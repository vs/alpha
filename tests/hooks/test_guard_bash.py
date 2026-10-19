import subprocess
from pathlib import Path

import pytest

from .conftest import Project

NO_VERIFY = "--no-verify skips the project's commit checks."


def bash(project: Project, command: str) -> subprocess.CompletedProcess[str]:
    return project.run_hook(
        "guard_bash.py", {"tool_name": "Bash", "tool_input": {"command": command}}
    )


@pytest.mark.parametrize(
    ("command", "needle"),
    [
        ("git commit -m x --no-verify", NO_VERIFY),
        ("git commit -nm x", NO_VERIFY),
        ("git commit -anm x", NO_VERIFY),
        ("git commit -n -m x", NO_VERIFY),
        ("git -C sub -c a=b commit --no-verify -m x", NO_VERIFY),
        ("FOO=1 git push --no-verify", NO_VERIFY),
        ("git merge --no-verify topic", NO_VERIFY),
        ("git rebase --no-verify main", NO_VERIFY),
        ("git cherry-pick --no-verify abc", NO_VERIFY),
        ("cd a && git push -f", "-f"),
        ("git push --force", "--force"),
        ("git push origin +main", "+main"),
        ("git push --force-with-lease", "--force-with-lease"),
        ("git push --force-if-includes", "--force-if-includes"),
        ("echo hi; git push -uf origin main", "-uf"),
        ("ls | git push -f", "-f"),
        ("echo hi\ngit push -f", "-f"),
        ("true || command git commit --no-verify", NO_VERIFY),
    ],
)
def test_blocked(project: Project, command: str, needle: str) -> None:
    result = bash(project, command)
    assert result.returncode == 2, result.stderr
    assert needle in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push -n",
        "git push --dry-run -u origin main",
        'git commit -m "mention --no-verify in text"',
        "git commit -m --no-verify",
        "git commit -mn",
        "echo git push -f",
        "ls -f",
        "git status && git log -n 3",
        "git commit -m 'unbalanced",
        "git push origin main -- +weird",
        "",
    ],
)
def test_allowed(project: Project, command: str) -> None:
    result = bash(project, command)
    assert result.returncode == 0, result.stderr


def test_non_bash_tool_ignored(project: Project) -> None:
    result = project.run_hook(
        "guard_bash.py",
        {"tool_name": "Write", "tool_input": {"command": "git push -f"}},
    )
    assert result.returncode == 0


def test_not_an_alpha_project_ignored(project: Project) -> None:
    (project.root / "docs" / "principles.toml").unlink()
    assert bash(project, "git push -f").returncode == 0


def test_amend_allowed_without_commits(project: Project) -> None:
    assert bash(project, "git commit --amend -m x").returncode == 0


def test_amend_allowed_without_remote(project: Project) -> None:
    project.git("commit", "--allow-empty", "-m", "feat: One")
    assert bash(project, "git commit --amend -m x").returncode == 0


def test_amend_allowed_on_detached_head(project: Project) -> None:
    project.git("commit", "--allow-empty", "-m", "feat: One")
    project.git("checkout", "-q", "--detach")
    assert bash(project, "git commit --amend -m x").returncode == 0


def test_amend_blocked_when_pushed(project: Project, tmp_path: Path) -> None:
    remote = tmp_path.parent / f"{tmp_path.name}-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    project.git("commit", "--allow-empty", "-m", "feat: One")
    project.git("remote", "add", "origin", str(remote))
    project.git("push", "-q", "origin", "HEAD")
    project.git("fetch", "-q", "origin")
    result = bash(project, "git commit --amend --no-edit")
    assert result.returncode == 2
    assert "HEAD is already pushed (" in result.stderr
    assert "origin/" in result.stderr
    assert "Make a new commit instead." in result.stderr
    project.git("commit", "--allow-empty", "-m", "feat: Two")
    assert bash(project, "git commit --amend --no-edit").returncode == 0
