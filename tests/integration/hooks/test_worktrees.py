"""pstack works from git worktrees while CLAUDE_PROJECT_DIR stays on the main
checkout, so every hook must act on the checkout the work happens in."""

import os
import subprocess
from pathlib import Path
from typing import Any

import _common
import pytest
import review

from .conftest import Project


def committed(project: Project) -> None:
    """main, committed and published."""
    project.git("checkout", "-q", "-B", "main")
    project.write("api/src/a.py", "x = 1\n")
    project.git("add", "-A")
    project.git("commit", "-q", "-m", "chore: Base")
    project.git("update-ref", "refs/remotes/origin/main", "HEAD")


def worktree(project: Project, branch: str = "topic") -> Path:
    path = project.root.parent / f"{project.root.name}-{branch}"
    project.git("worktree", "add", "-q", "-b", branch, str(path))
    return path


def bash(
    project: Project,
    command: str,
    cwd: Path | None = None,
    env: dict[str, str | None] | None = None,
) -> subprocess.CompletedProcess[str]:
    payload: dict[str, Any] = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return project.run_hook("guard_bash.py", payload, env=env)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def gh_reporting_head(project: Project, checkout: Path) -> dict[str, str | None]:
    """An environment whose gh reports `checkout`'s HEAD as the pull
    request's head on GitHub."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout, capture_output=True, text=True
    ).stdout.strip()
    folder = project.root.parent / "fake-gh"
    folder.mkdir(exist_ok=True)
    gh = folder / "gh"
    gh.write_text(f'#!/bin/sh\necho \'{{"headRefOid": "{head}"}}\'\n')
    gh.chmod(0o755)
    return {"PATH": f"{folder}:{os.environ['PATH']}"}


def mark_reviewed(root: Path) -> None:
    """A clean review of HEAD's tree in `root`, committing the work first."""
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", "chore: Work")
    review.write_note(
        root,
        review.tree_of(root, "HEAD"),
        {"kind": "review", "branch": review.current_branch(root), "findings": []},
    )


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
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "feat: Add b")
    proc = bash(project, "gh pr merge topic --squash")
    assert proc.returncode == 2
    assert proc.stderr.startswith(
        "Nothing reaches main unreviewed: run the principles-reviewer agent "
        "first (1 file changed since the last review)."
    )
    mark_reviewed(wt)
    proc = bash(project, "gh pr merge topic --squash")
    assert proc.returncode == 2
    assert proc.stderr.startswith("Nothing reaches main untested: the tests of api ")
    assert project.run_tests(cwd=wt).returncode == 0
    env = gh_reporting_head(project, wt)
    assert bash(project, "gh pr merge topic --squash", env=env).returncode == 0
    assert bash(project, "gh pr merge --squash", cwd=wt, env=env).returncode == 0


def test_merge_is_blocked_when_gh_cannot_report_the_pr_head(project: Project) -> None:
    """Offline, signed out or timed out, gh can't say where the pull request's
    head is on GitHub, so alpha can't tell that what merges was reviewed."""
    committed(project)
    wt = worktree(project)
    mark_reviewed(wt)
    assert project.run_tests(cwd=wt).returncode == 0
    proc = bash(project, "gh pr merge topic", env={"PATH": "/usr/bin:/bin"})
    assert proc.returncode == 2
    assert "can't ask GitHub where pull request topic's head is" in proc.stderr


def test_a_merge_of_a_branch_not_checked_out_is_blocked(project: Project) -> None:
    """Merging from main a pull request whose branch isn't checked out here
    would skip its review and test gates."""
    committed(project)
    elsewhere = bash(project, "gh pr merge elsewhere")
    assert elsewhere.returncode == 2
    assert "elsewhere isn't checked out here" in elsewhere.stderr
    proc = project.run_hook(
        "guard_bash.py",
        {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 12"}},
        env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 2
    assert "can't tell which branch pull request 12 merges" in proc.stderr


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
    (wt / "CONTRIBUTING.md").write_text(
        "# Contributing\n\n## Exceptions\n\n| Path | Check | Reason |\n|---|---|---|\n"
        "| `api/src/a.py` | `# type: ignore` | Untyped upstream. |\n"
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
    assert review.last_review(project.root) is None
    assert review.files_to_review(project.root, None) == ["api/src/b.py"]


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
    project.git("update-ref", "refs/remotes/origin/main", "HEAD")  # as a fetch
    project.git("checkout", "-q", "topic")
    project.git("rebase", "-q", "main")
    last = review.last_review(project.root)
    assert last is not None
    assert review.files_to_review(project.root, last[0]) == []
    project.write("api/src/b.py", "y = 3\n")
    project.git("add", "api/src/b.py")
    project.git("commit", "-q", "-m", "fix: Change b")
    assert review.files_to_review(project.root, last[0]) == ["api/src/b.py"]


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
