import hashlib
import json
import threading
from pathlib import Path
from typing import Any

import pytest
import review

from .conftest import Project

FINDING = {
    "principle": "fail-helpfully",
    "file": "api/src/x.py",
    "line": 3,
    "problem": "The except clause swallows every error.",
    "fix": "Catch the specific error and say how to fix it.",
}


def setup(project: Project) -> str:
    project.write("api/pyproject.toml", "[project]\n")
    project.git("add", "-A")
    project.git("commit", "-q", "-m", "chore: Base")
    review.ensure_state(project.root)
    project.write("api/src/x.py", "x = 1\n")
    return review.brief(project.root).splitlines()[0].removeprefix("Tree: ")


def report(tree: str, findings: list[dict[str, Any]]) -> str:
    body = json.dumps({"tree": tree, "findings": findings})
    return f"Reviewed the changes.\n\n```json\n{body}\n```"


def record(
    project: Project,
    message: str,
    agent_type: str = "principles-reviewer",
    transcript: list[dict[str, Any]] | None = None,
):
    payload: dict[str, Any] = {
        "hook_event_name": "SubagentStop",
        "agent_id": "r1",
        "agent_type": agent_type,
        "stop_hook_active": False,
        "last_assistant_message": message,
    }
    if transcript is not None:
        path = project.root / ".claude/alpha/state/agent-r1.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in transcript))
        payload["agent_transcript_path"] = str(path)
    return project.run_hook("review_record.py", payload)


def asked(text: str) -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": text}}


def said(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"type": "assistant", "message": {"role": "assistant", "content": blocks}}


def handed_back(text: str) -> dict[str, Any]:
    call = {"type": "tool_use", "name": "SubagentHandback", "input": {"message": text}}
    return said(call)


def finding_id(f: dict[str, Any]) -> str:
    key = f"{f['principle']}|{f['file']}|{f['problem']}"
    return "F-" + hashlib.sha1(key.encode()).hexdigest()[:6]


def test_clean_report_advances_to_the_reported_tree(project: Project) -> None:
    tree = setup(project)
    project.write("api/src/y.py", "y = 2\n")
    proc = record(project, report(tree, []))
    assert proc.returncode == 0 and proc.stdout == ""
    state = review.load_state(project.root)
    assert state["reviewed_tree"] == tree
    assert state["findings"] == []
    assert review.debt(project.root, project.principles())["files"] == ["api/src/y.py"]


def test_findings_are_recorded_with_stable_ids(project: Project) -> None:
    tree = setup(project)
    before = review.load_state(project.root)["reviewed_tree"]
    assert record(project, report(tree, [FINDING])).stdout == ""
    state = review.load_state(project.root)
    assert state["reviewed_tree"] == before
    assert state["reviewed_for"] == tree
    assert state["findings"] == [
        {"id": finding_id(FINDING), **FINDING, "accepted": False}
    ]


def test_accepted_flag_survives_a_re_review(project: Project) -> None:
    tree = setup(project)
    record(project, report(tree, [FINDING]))
    state = review.load_state(project.root)
    state["findings"][0]["accepted"] = True
    review.save_state(project.root, state)
    record(project, report(tree, [FINDING]))
    assert review.load_state(project.root)["findings"][0]["accepted"] is True


@pytest.mark.parametrize(
    "message",
    [
        "Looks fine to me.",
        "```json\n{not json}\n```",
        report("0" * 40, []),
        report("abc", []),
        "```json\n"
        + json.dumps({"tree": "TREE", "findings": [{"principle": "x"}]})
        + "\n```",
        "```json\n"
        + json.dumps({"tree": "TREE", "findings": [{**FINDING, "line": "3"}]})
        + "\n```",
    ],
)
def test_malformed_reports_send_the_reviewer_back(
    project: Project, message: str
) -> None:
    tree = setup(project)
    proc = record(project, message.replace("TREE", tree))
    out = json.loads(proc.stdout)
    assert out["decision"] == "block"
    assert "End your report with one fenced json block" in out["reason"]
    assert "review.py brief" in out["reason"]
    assert review.load_state(project.root).get("findings") == []


def test_other_agents_are_ignored(project: Project) -> None:
    tree = setup(project)
    proc = record(project, report(tree, []), agent_type="general-purpose")
    assert proc.stdout == ""
    assert review.load_state(project.root)["reviewed_tree"] != tree


def test_last_json_block_wins(project: Project) -> None:
    tree = setup(project)
    message = 'Example:\n```json\n{"tree": "x"}\n```\n' + report(tree, [])
    assert record(project, message).stdout == ""
    assert review.load_state(project.root)["reviewed_tree"] == tree


def test_a_report_handed_back_is_recorded(project: Project) -> None:
    tree = setup(project)
    transcript = [
        asked("Review the branch."),
        said({"type": "text", "text": "Reading the brief."}),
        {"type": "user", "isMeta": True, "message": {"content": "Hand back now."}},
        handed_back(report(tree, [FINDING])),
    ]
    assert record(project, "", transcript=transcript).stdout == ""
    state = review.load_state(project.root)
    assert state["reviewed_for"] == tree
    assert [f["id"] for f in state["findings"]] == [finding_id(FINDING)]


def test_a_report_from_an_earlier_request_is_not_this_one(project: Project) -> None:
    tree = setup(project)
    transcript = [
        asked("Review the branch."),
        handed_back(report(tree, [])),
        asked("Review it again after the fix."),
        said({"type": "text", "text": "Done."}),
    ]
    out = json.loads(record(project, "Done.", transcript=transcript).stdout)
    assert out["decision"] == "block"
    assert "no json block" in out["reason"]


def stopped(project: Project, transcript: Path):
    return project.run_hook(
        "review_record.py",
        {
            "hook_event_name": "SubagentStop",
            "agent_type": "principles-reviewer",
            "agent_transcript_path": str(transcript),
        },
    )


def test_a_transcript_mid_write_still_gives_the_report(project: Project) -> None:
    tree = setup(project)
    path = project.root / ".claude/alpha/state/agent-r1.jsonl"
    lines = [asked("Review the branch."), handed_back(report(tree, []))]
    cut = '{"type": "assistant", "message": {"content": "caf\u00e9'.encode()[:-1]
    path.write_bytes("".join(json.dumps(e) + "\n" for e in lines).encode() + cut)
    assert stopped(project, path).stdout == ""
    assert review.load_state(project.root)["reviewed_tree"] == tree


def test_a_hand_back_written_after_the_hook_starts_is_found(project: Project) -> None:
    tree = setup(project)
    path = project.root / ".claude/alpha/state/agent-r1.jsonl"
    path.write_text(json.dumps(asked("Review the branch.")) + "\n")
    late = json.dumps(handed_back(report(tree, []))) + "\n"

    def append() -> None:
        with path.open("a") as f:
            f.write(late)

    timer = threading.Timer(0.3, append)
    timer.start()
    proc = stopped(project, path)
    timer.join()
    assert proc.stdout == ""
    assert review.load_state(project.root)["reviewed_tree"] == tree
