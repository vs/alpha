"""pstack works from git worktrees while CLAUDE_PROJECT_DIR stays on the main
checkout, so every hook must act on the checkout the work happens in."""

import subprocess
from pathlib import Path
from typing import Any

import _common
import pytest
import review

from .conftest import Project


def committed(project: Project) -> None:
    project.git("checkout", "-q", "-B", "main")
    project.write("api/src/a.py", "x = 1\n")
    project.git("add", "-A")
    project.git("commit", "-q", "-m", "chore: Base")
    state = review.ensure_state(project.root)
    state["reviewed_tree"] = review.snapshot(project.root)
    review.save_state(project.root, state)


def worktree(project: Project, branch: str = "topic") -> Path:
    path = project.root.parent / f"{project.root.name}-{branch}"
    project.git("worktree", "add", "-q", "-b", branch, str(path))
    return path


def bash(
    project: Project, command: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    payload: dict[str, Any] = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return project.run_hook("guard_bash.py", payload)


def mark_reviewed(root: Path) -> None:
    state = review.ensure_state(root)
    state["reviewed_tree"] = review.snapshot(root)
    review.save_state(root, state)


@pytest.mark.parametrize(
    "command",
    [
        "git push --force-with-lease",
        "git push --force-with-lease origin HEAD",
    ],
)
def test_a_lease_push_from_a_worktree_judges_its_branch(
    project: Project, command: str
) -> None:
    committed(project)
    wt = worktree(project)
    assert bash(project, command, cwd=wt).returncode == 0
    assert bash(project, f"cd {wt} && {command}").returncode == 0
    assert bash(project, command.replace("git ", f"git -C {wt} ", 1)).returncode == 0
    blocked = bash(project, command)
    assert blocked.returncode == 2
    assert "would rewrite the main branch" in blocked.stderr


def test_merge_checks_the_checkout_that_has_the_branch(project: Project) -> None:
    committed(project)
    wt = worktree(project)
    (wt / "api/src/b.py").write_text("y = 2\n")
    proc = bash(project, "gh pr merge topic --squash")
    assert proc.returncode == 2
    assert proc.stderr.startswith(
        "Nothing reaches main unreviewed: run the principles-reviewer agent "
        "first (1 file changed since the last review)."
    )
    mark_reviewed(wt)
    assert bash(project, "gh pr merge topic --squash").returncode == 0
    assert bash(project, "gh pr merge --squash", cwd=wt).returncode == 0


def test_merge_of_a_branch_no_checkout_has_says_where_to_review(
    project: Project,
) -> None:
    committed(project)
    proc = bash(project, "gh pr merge elsewhere")
    assert proc.returncode == 2
    assert "no checkout here has elsewhere" in proc.stderr
    assert "git worktree add <folder> elsewhere" in proc.stderr


def test_merge_by_a_number_gh_cannot_resolve_is_explained(project: Project) -> None:
    committed(project)
    proc = project.run_hook(
        "guard_bash.py",
        {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 12"}},
        env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 2
    assert "can't tell which branch `gh pr merge 12` merges" in proc.stderr


def test_edits_in_a_worktree_are_checked_against_it(project: Project) -> None:
    committed(project)
    wt = worktree(project)
    edit = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(wt / "api/src/a.py"),
            "old_string": "x = 1",
            "new_string": "x = 1  # type: ignore",
        },
    }
    proc = project.run_hook("guard_paths.py", edit)
    assert proc.returncode == 2
    assert "in api/src/a.py." in proc.stderr
    record = wt / "docs/decisions/0001-keep-the-ignore.md"
    record.parent.mkdir(parents=True)
    record.write_text(
        "# 0001. Keep the ignore\n\nDate: 2026-11-11\nStatus: accepted\n\n"
        "## Decision\n\napi/src/a.py keeps `# type: ignore`.\n"
    )
    assert project.run_hook("guard_paths.py", edit).returncode == 0
    secret = {"tool_name": "Write", "tool_input": {"file_path": str(wt / ".env")}}
    assert project.run_hook("guard_paths.py", secret).returncode == 2


def test_a_pushed_branch_is_not_taken_as_reviewed(
    project: Project, tmp_path: Path
) -> None:
    committed(project)
    remote = tmp_path.parent / f"{tmp_path.name}-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    project.git("remote", "add", "origin", str(remote))
    project.git("push", "-q", "origin", "main")
    project.git("checkout", "-q", "-b", "topic")
    project.write("api/src/b.py", "y = 2\n")
    project.git("add", "api/src/b.py")
    project.git("commit", "-q", "-m", "feat: Add b")
    project.git("push", "-q", "-u", "origin", "topic")
    (project.root / ".claude/alpha/state/review.json").unlink()
    assert review.debt(project.root, project.principles())["files"] == ["api/src/b.py"]


def test_a_rebase_onto_main_keeps_the_review(project: Project) -> None:
    committed(project)
    project.git("checkout", "-q", "-b", "topic")
    project.write("api/src/b.py", "y = 2\n")
    project.git("add", "api/src/b.py")
    project.git("commit", "-q", "-m", "feat: Add b")
    mark_reviewed(project.root)
    project.git("checkout", "-q", "main")
    project.write("web/src/c.ts", "export const c = 3\n")
    project.git("add", "web/src/c.ts")
    project.git("commit", "-q", "-m", "feat: Add c")
    project.git("checkout", "-q", "topic")
    project.git("rebase", "-q", "main")
    assert review.debt(project.root, project.principles())["files"] == []
    project.write("api/src/b.py", "y = 3\n")
    assert review.debt(project.root, project.principles())["files"] == ["api/src/b.py"]


def test_project_root_prefers_the_file_then_the_cwd(
    project: Project, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    committed(project)
    wt = worktree(project)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project.root))
    root = project.root.resolve()
    assert _common.project_root({}, str(wt / "api/new/x.py")) == wt.resolve()
    assert _common.project_root({"cwd": str(wt / "api")}) == wt.resolve()
    assert _common.project_root({"cwd": str(wt)}, "/elsewhere/x.py") == wt.resolve()
    assert _common.project_root({"cwd": str(project.root / "api")}) == root
    outside = tmp_path.parent / "not-a-project"
    outside.mkdir(exist_ok=True)
    assert _common.project_root({"cwd": str(outside)}) == project.root
