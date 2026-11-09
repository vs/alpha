import json
import subprocess

import review

from .conftest import Project

FINDING = {
    "principle": "safe-migrations",
    "file": "api/migrations/0001.sql",
    "line": 1,
    "problem": "The migration can't be reversed.",
    "fix": "Add a down migration.",
}


def hook(project: Project, script: str, payload: dict[str, object]):
    return project.run_hook(script, payload)


def report(project: Project, tree: str, findings: list[dict[str, object]]):
    body = json.dumps({"tree": tree, "findings": findings})
    return hook(
        project,
        "review_record.py",
        {
            "hook_event_name": "SubagentStop",
            "agent_type": "principles-reviewer",
            "last_assistant_message": f"Done.\n\n```json\n{body}\n```",
        },
    )


def stop(project: Project) -> subprocess.CompletedProcess[str]:
    return hook(project, "stop_checks.py", {"hook_event_name": "Stop"})


def started(project: Project) -> None:
    project.write("api/pyproject.toml", "[project]\n")
    project.write("web/package.json", "{}\n")
    project.git("add", "-A")
    project.git("commit", "-q", "-m", "chore: Base")
    review.ensure_state(project.root)
    project.write("api/migrations/0001.sql", "create table t (id int);\n")


def test_accepting_and_recording_clears_the_review(project: Project) -> None:
    started(project)
    tree = review.brief(project.root).splitlines()[0].removeprefix("Tree: ")
    assert report(project, tree, [FINDING]).stdout == ""
    (finding,) = review.load_state(project.root)["findings"]
    prompt = hook(
        project,
        "user_prompt.py",
        {"hook_event_name": "UserPromptSubmit", "prompt": f"accept {finding['id']}"},
    )
    assert "accepted" in prompt.stdout
    project.write(
        "docs/decisions/0001-keep-the-migration.md",
        "# 0001. Keep the migration\n\nDate: 2026-10-23\nStatus: accepted\n"
        f"Accepts: {finding['id']}\n\n## Context\n\nc\n\n## Decision\n\nd\n\n"
        "## Consequences\n\nq\n",
    )
    proc = stop(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout
    state = review.load_state(project.root)
    assert state["findings"] == [] and state["reviewed_tree"] == tree


def test_brief_lists_accepted_findings_not_to_report_again(project: Project) -> None:
    started(project)
    tree = review.brief(project.root).splitlines()[0].removeprefix("Tree: ")
    report(project, tree, [FINDING])
    state = review.load_state(project.root)
    state["findings"][0]["accepted"] = True
    review.save_state(project.root, state)
    text = review.brief(project.root)
    assert "## Accepted findings (don't report these again)" in text
    assert f"- {state['findings'][0]['id']} safe-migrations" in text


def test_a_report_on_the_reviewed_tree_is_sent_back(project: Project) -> None:
    started(project)
    lines = review.brief(project.root).splitlines()
    reviewed = lines[1].removeprefix("Reviewed: ")
    out = json.loads(report(project, reviewed, []).stdout)
    assert out["decision"] == "block"
    assert "Tree line" in out["reason"] and "not its Reviewed line" in out["reason"]
    assert review.load_state(project.root)["reviewed_tree"] == reviewed


def prompt(project: Project, text: str = "next task") -> None:
    hook(
        project,
        "user_prompt.py",
        {"hook_event_name": "UserPromptSubmit", "prompt": text},
    )


def test_changes_between_turns_are_not_claudes_debt(project: Project) -> None:
    started(project)
    (project.root / "api/migrations/0001.sql").unlink()
    assert stop(project).stdout == ""
    project.write("api/migrations/0002.sql", "alter table t add c int;\n")
    prompt(project)
    debt = review.debt(project.root, project.principles())
    assert debt["files"] == []
    assert stop(project).stdout == ""


def test_claudes_unreviewed_work_stays_debt(project: Project) -> None:
    started(project)
    blocked = json.loads(stop(project).stdout)
    assert "principles-reviewer" in blocked["reason"]
    project.write("web/README.md", "notes\n")
    prompt(project)
    debt = review.debt(project.root, project.principles())
    assert debt["files"] == ["api/migrations/0001.sql"]


def test_a_conflicting_outside_change_stays_debt(project: Project) -> None:
    started(project)
    stop(project)
    project.write("api/migrations/0001.sql", "create table u (id int);\n")
    prompt(project)
    debt = review.debt(project.root, project.principles())
    assert debt["files"] == ["api/migrations/0001.sql"]
