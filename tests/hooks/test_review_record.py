import hashlib
import json
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
    # The reviewer works from the brief, which hands out the tree to report.
    return review.brief(project.root).splitlines()[0].removeprefix("Tree: ")


def report(tree: str, findings: list[dict[str, Any]]) -> str:
    body = json.dumps({"tree": tree, "findings": findings})
    return f"Reviewed the changes.\n\n```json\n{body}\n```"


def record(project: Project, message: str, agent_type: str = "principles-reviewer"):
    return project.run_hook(
        "review_record.py",
        {
            "hook_event_name": "SubagentStop",
            "agent_id": "r1",
            "agent_type": agent_type,
            "stop_hook_active": False,
            "last_assistant_message": message,
        },
    )


def finding_id(f: dict[str, Any]) -> str:
    key = f"{f['principle']}|{f['file']}|{f['problem']}"
    return "F-" + hashlib.sha1(key.encode()).hexdigest()[:6]


def test_clean_report_advances_to_the_reported_tree(project: Project) -> None:
    tree = setup(project)
    project.write("api/src/y.py", "y = 2\n")  # edited while the review ran
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
    assert state["reviewed_tree"] == before  # not reviewed until it passes
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
