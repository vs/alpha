"""The principles review in git notes on trees (spec, R9 and R10)."""

import json
from typing import Any

import pytest
import review

from .conftest import Project

FINDING = {
    "principle": "fail-helpfully",
    "file": "api/src/a.py",
    "line": 1,
    "problem": "It swallows every error.",
    "fix": "Catch the specific error.",
}


def commit(project: Project, rel: str, text: str = "x = 1\n") -> str:
    project.write(rel, text)
    project.git("add", "-A")
    project.git("commit", "-q", "-m", f"feat: Change {rel}")
    return project.git("rev-parse", "HEAD^{tree}").stdout.strip()


def on_a_branch(project: Project) -> None:
    """main published at a base commit, and a feature branch off it."""
    commit(project, "README.md", "# Base\n")
    project.git("update-ref", "refs/remotes/origin/main", "HEAD")
    project.git("switch", "-q", "-c", "feature")


def reviewed(project: Project, findings: list[dict[str, Any]] | None = None) -> str:
    """Brief the current tree and record a review of it, as the hook does."""
    tree = review.brief(project.root).splitlines()[0].removeprefix("Tree: ")
    brief = next(b for b in review.briefs(project.root) if b["tree"] == tree)
    review.write_note(
        project.root,
        tree,
        {
            "kind": brief["kind"],
            "branch": brief["branch"],
            "base": brief["base"],
            "recorded": len(review.briefs(project.root)),
            "findings": [
                {"id": f"F-{i:06x}", **f, "status": "open"}
                for i, f in enumerate(findings or [])
            ],
        },
    )
    return tree


def gate(project: Project) -> str | None:
    return review.gate(project.root, project.principles())


def test_R9_2_merge_waits_for_a_review_of_the_head_tree(project: Project) -> None:
    on_a_branch(project)
    assert gate(project) is None  # nothing to review yet
    commit(project, "api/src/a.py")
    blocked = gate(project)
    assert blocked is not None and blocked.startswith(
        "Nothing reaches main unreviewed: run the principles-reviewer agent first "
        "(1 file changed since the last review)."
    )
    reviewed(project)
    assert gate(project) is None
    project.write("api/src/a.py", "x = 2\n")
    dirty = gate(project)
    assert dirty is not None and "Commit or stash the changes" in dirty
    with pytest.raises(review.ReviewError, match="uncommitted changes"):
        review.brief(project.root)


def test_R9_3_a_fix_check_reviews_only_whats_new(project: Project) -> None:
    on_a_branch(project)
    commit(project, "api/src/a.py")
    commit(project, "api/src/b.py")
    other = {**FINDING, "file": "api/src/b.py", "problem": "It reads too much."}
    reviewed(project, [FINDING, other])
    blocked = gate(project)
    assert blocked is not None and "F-000000, F-000001" in blocked
    commit(project, "api/src/a.py", "x = 2\n")  # the fix
    project.git(
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "chore: Keep b\n\nAccepts: F-000001 Reads are bounded.",
    )
    commit(project, "api/src/c.py")  # new work
    text = review.brief(project.root)
    assert "Kind: fix-check" in text
    assert "- F-000000 fail-helpfully api/src/a.py:1" in text
    assert "Accepts: F-000001 Reads are bounded." in text
    fresh = text.split("## Review afresh\n\n")[1].split("\n\n")[0]
    assert fresh.splitlines() == ["- api/src/c.py"]
    tree = text.splitlines()[0].removeprefix("Tree: ")
    brief = next(b for b in review.briefs(project.root) if b["tree"] == tree)
    assert brief["fresh"] == ["api/src/c.py"]
    note: dict[str, Any] = {
        "kind": "fix-check",
        "branch": "feature",
        "base": brief["base"],
        "findings": [
            {**f, "status": "fixed" if f["id"] == "F-000000" else "accepted"}
            for f in brief["findings"]
        ],
    }
    review.write_note(project.root, tree, note)
    assert gate(project) is None


def test_R9_3_a_fix_check_record_refuses_new_findings_on_reviewed_files(
    project: Project,
) -> None:
    on_a_branch(project)
    commit(project, "api/src/a.py")
    reviewed(project, [FINDING])
    commit(project, "api/src/a.py", "x = 2\n")
    commit(project, "api/src/c.py")
    tree = review.brief(project.root).splitlines()[0].removeprefix("Tree: ")
    again = {**FINDING, "problem": "Another thing in the same file."}
    body = json.dumps({"tree": tree, "checked": [], "findings": [again]})
    proc = project.run_hook(
        "review_record.py",
        {
            "hook_event_name": "SubagentStop",
            "agent_type": "principles-reviewer",
            "last_assistant_message": f"```json\n{body}\n```",
        },
    )
    out = json.loads(proc.stdout)
    assert out["decision"] == "block"
    assert "doesn't review afresh" in out["reason"] and "api/src/c.py" in out["reason"]


def test_a_risk_path_finding_isnt_accepted_by_the_fix_check(project: Project) -> None:
    on_a_branch(project)
    commit(project, "api/migrations/0001.sql", "create table t (id int);\n")
    risky = {**FINDING, "file": "api/migrations/0001.sql"}
    reviewed(project, [risky])
    project.git("commit", "-q", "--allow-empty", "-m", "chore: Keep it")
    tree = review.brief(project.root).splitlines()[0].removeprefix("Tree: ")
    body = json.dumps(
        {
            "tree": tree,
            "checked": [{"id": "F-000000", "status": "accepted"}],
            "findings": [],
        }
    )
    project.run_hook(
        "review_record.py",
        {
            "hook_event_name": "SubagentStop",
            "agent_type": "principles-reviewer",
            "last_assistant_message": f"```json\n{body}\n```",
        },
    )
    recorded = review.read_note(project.root, tree)
    assert recorded is not None and recorded["findings"][0]["status"] == "open"
    blocked = gate(project)
    assert blocked is not None and 'replying "accept F-000000"' in blocked


def test_R10_2_the_last_reviewed_tree_is_found_in_history(project: Project) -> None:
    on_a_branch(project)
    commit(project, "api/src/a.py")
    b = reviewed(project)
    commit(project, "api/src/c.py")
    last = review.last_review(project.root)
    assert last is not None and last[0] == b
    # A merge from main after B keeps B as the last review.
    project.git("switch", "-q", "-c", "upstream", "refs/remotes/origin/main")
    commit(project, "web/src/m.ts", "export const m = 1;\n")
    project.git("update-ref", "refs/remotes/origin/main", "HEAD")
    project.git("switch", "-q", "feature")
    project.git("merge", "-q", "--no-edit", "upstream")
    last = review.last_review(project.root)
    assert last is not None and last[0] == b
    # A rebase gives every commit a new tree: the branch's newest note.
    project.git("rebase", "-q", "upstream")
    last = review.last_review(project.root)
    assert last is not None and last[0] == b


def test_R10_2_a_note_on_main_carries_nothing_into_a_branch(project: Project) -> None:
    commit(project, "api/src/a.py")
    reviewed(project, [FINDING])  # on main, with an open finding
    project.git("update-ref", "refs/remotes/origin/main", "HEAD")
    project.git("switch", "-q", "-c", "feature")
    commit(project, "api/src/c.py")
    assert review.last_review(project.root) is None
    text = review.brief(project.root)
    assert "Kind: review" in text and "F-000000" not in text


def test_R10_3_the_brief_holds_only_files_changed_since(project: Project) -> None:
    on_a_branch(project)
    commit(project, "api/src/a.py")
    reviewed(project)
    commit(project, "api/src/c.py")
    text = review.brief(project.root)
    changed = text.split("## Changed files\n\n")[1].split("\n\n")[0]
    assert changed.splitlines() == ["- api/src/c.py"]
    diff = text.split("## Diff")[1]
    assert "diff --git a/api/src/c.py b/api/src/c.py" in diff
    assert "api/src/a.py" not in diff


def test_R10_3_alphas_own_writes_are_left_out(project: Project) -> None:
    on_a_branch(project)
    tree = commit(project, ".claude/alpha/hooks/x.py", "# alpha's\n")
    render = project.git("commit-tree", tree, "-m", "alpha render").stdout.strip()
    project.git("notes", "--ref=alpha-rendered", "add", "-m", render, "HEAD")
    commit(project, "api/src/a.py")
    assert review.files_to_review(project.root, None) == ["api/src/a.py"]


ANSWERS = ".claude/alpha/project.json"


def answers_on_main(project: Project) -> dict[str, Any]:
    """main with an adopted project's answers, and a feature branch off it."""
    data: dict[str, Any] = {
        "releases": {"process": "Tag vX.Y.Z on main."},
        "installed": {"kit_version": "1.1.0"},
        "adoption": {
            "steps": [{"id": "p4-a", "status": "pending", "reason": ""}],
        },
    }
    commit(project, ANSWERS, json.dumps(data, indent=2))
    project.git("update-ref", "refs/remotes/origin/main", "HEAD")
    project.git("switch", "-q", "-c", "feature")
    return data


def test_alphas_records_in_the_answers_need_no_review(project: Project) -> None:
    """alpha update moves installed.kit_version and alpha adopt start and done
    set a step's status and branch: alpha's own records, not decisions."""
    data = answers_on_main(project)
    data["installed"]["kit_version"] = "1.1.1"
    data["adoption"]["steps"][0].update(status="done", branch="alpha/p4-a")
    commit(project, ANSWERS, json.dumps(data, indent=2))
    assert review.files_to_review(project.root, None) == []
    assert gate(project) is None


@pytest.mark.parametrize("changed", ["an answer", "a dropped step's reason"])
def test_a_changed_answer_is_still_reviewed(project: Project, changed: str) -> None:
    data = answers_on_main(project)
    data["installed"]["kit_version"] = "1.1.1"
    if changed == "an answer":
        data["releases"]["process"] = "Tag and publish."
    else:
        data["adoption"]["steps"][0]["reason"] = "not worth it"
    commit(project, ANSWERS, json.dumps(data, indent=2))
    assert review.files_to_review(project.root, None) == [ANSWERS]


def test_R10_2_a_merged_branch_note_carries_nothing_into_its_next_work(
    project: Project,
) -> None:
    """A branch reviewed with an open finding, merged as it was, then reused
    under the same name: its old note isn't this work's last review."""
    on_a_branch(project)
    commit(project, "api/src/a.py")
    reviewed(project, [FINDING])
    project.git("update-ref", "refs/remotes/origin/main", "HEAD")  # merged
    commit(project, "api/src/c.py")
    assert review.last_review(project.root) is None


def test_R17_1_the_review_leaves_out_not_code(project: Project) -> None:
    project.set_not_code("examples")
    on_a_branch(project)
    commit(project, "examples/app.py")
    assert gate(project) is None  # only not-code changes: nothing to review
    commit(project, "api/src/a.py")
    text = review.brief(project.root)
    changed = text.split("## Changed files\n\n")[1].split("\n\n")[0]
    assert changed.splitlines() == ["- api/src/a.py"]
    skipped = text.split("## Not code (not reviewed)\n\n")[1].split("\n\n")[0]
    assert skipped.splitlines() == ["- examples/app.py"]
    assert "examples/app.py" not in text.split("## Diff")[1]
    rules = text.split("## Stack rules\n\n")[1].split("\n\n")[0]
    assert "python:" in rules and "typescript:" not in rules
    blocked = gate(project)
    assert blocked is not None and "(1 file changed since" in blocked
