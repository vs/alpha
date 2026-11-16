"""The user's `accept F-xxxxxx` (spec, R9.4)."""

import json

import review

from .conftest import Project

RISKY = {
    "id": "F-abc123",
    "principle": "safe-migrations",
    "file": "api/migrations/0001.sql",
    "line": 1,
    "problem": "It edits a migration.",
    "fix": "Add a new one.",
    "status": "open",
}


def noted(project: Project) -> str:
    project.write("README.md", "# Base\n")
    project.git("add", "-A")
    project.git("commit", "-q", "-m", "chore: Base")
    project.git("update-ref", "refs/remotes/origin/main", "HEAD")
    project.git("switch", "-q", "-c", "feature")
    project.write("api/migrations/0001.sql", "create table t (id int);\n")
    project.git("add", "-A")
    project.git("commit", "-q", "-m", "feat: Add a table")
    tree = project.git("rev-parse", "HEAD^{tree}").stdout.strip()
    review.write_note(
        project.root,
        tree,
        {"kind": "review", "branch": "feature", "base": "", "findings": [RISKY]},
    )
    return tree


def prompt(project: Project, text: str):
    return project.run_hook(
        "accept.py", {"hook_event_name": "UserPromptSubmit", "prompt": text}
    )


def test_R9_4_only_the_users_prompt_accepts_a_risk_path_finding(
    project: Project,
) -> None:
    tree = noted(project)
    project.git("commit", "-q", "--allow-empty", "-m", "x\n\nAccepts: F-abc123 Fine.")
    assert review.gate(project.root, project.principles()) is not None
    said = prompt(project, "please accept F-abc123 now")
    assert "nothing was accepted" not in said.stdout  # not the command at all
    unchanged = review.read_note(project.root, tree)
    assert unchanged is not None and unchanged["findings"][0]["status"] == "open"
    near = prompt(project, "accept F-abc123 please")
    assert (
        "nothing was accepted"
        in json.loads(near.stdout)["hookSpecificOutput"]["additionalContext"]
    )
    done = prompt(project, "accept F-abc123")
    context = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
    assert context.startswith("alpha: the user accepted F-abc123")
    recorded = review.read_note(project.root, tree)
    assert recorded is not None
    assert recorded["findings"][0]["status"] == "accepted"
    assert recorded["findings"][0]["accepted_by"] == "user"
    assert review.gate(project.root, project.principles()) is None


def test_an_unknown_id_accepts_nothing(project: Project) -> None:
    noted(project)
    out = prompt(project, "accept F-000000")
    context = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "isn't an open review finding" in context and "F-abc123" in context
