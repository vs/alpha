"""alpha uninstall and alpha hooks on (rewrite spec, R1.4, R2.1 and R2.2)."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from helpers import (
    adoption_answers,
    existing_repo,
    generated_repo,
    git,
    install,
    run_cli,
)

from alpha.status import status

SETTINGS = ".claude/settings.json"
ALPHA_HOOKS = ".claude/alpha/hooks/"
MINE = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}
CHAINED = """#!/bin/sh
set -e
echo "husky runs first"
# alpha:begin
sh .claude/alpha/githooks/commit-msg "$1"
# alpha:end
echo "husky runs last"
"""


def commands(target: Path) -> list[str]:
    hooks: dict[str, Any] = json.loads((target / SETTINGS).read_text()).get("hooks", {})
    return [
        h["command"] for groups in hooks.values() for g in groups for h in g["hooks"]
    ]


def hooks_path(target: Path) -> str | None:
    done = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=target,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else None


def bad_commit(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "added a thing"],
        cwd=target,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def project(tmp_path: Path, git_env: None) -> Path:
    """A new project, committed, whose settings also hold the user's own
    hook and permission."""
    repo = generated_repo(tmp_path / "p", "python-ml-single")
    settings = json.loads((repo / SETTINGS).read_text())
    settings["hooks"]["PreToolUse"].append(MINE)
    settings["permissions"]["allow"].append("Bash(make *)")
    (repo / SETTINGS).write_text(json.dumps(settings, indent=2) + "\n")
    git(repo, "add", SETTINGS)
    git(repo, "commit", "-q", "-m", "chore: Add my own hook")
    return repo


@pytest.fixture
def chained(tmp_path: Path, git_env: None) -> Path:
    """An adopted repo whose own hook manager (husky's layout) calls alpha's
    commit check between the markers."""
    repo = existing_repo(tmp_path / "repo")
    adoption_answers(repo, git_hooks="chain")
    install(repo)
    hook = repo / ".husky/commit-msg"
    hook.parent.mkdir()
    hook.write_text(CHAINED)
    hook.chmod(0o755)
    git(repo, "config", "core.hooksPath", ".husky")
    return repo


def test_R2_1_uninstall_removes_only_the_hook_wiring(project: Path) -> None:
    before = json.loads((project / SETTINGS).read_text())
    head = git(project, "rev-parse", "HEAD")
    done = run_cli("uninstall", str(project))
    assert done.returncode == 0, done.stderr
    assert "removed alpha's hook entries" in done.stdout
    after = json.loads((project / SETTINGS).read_text())
    assert not [c for c in commands(project) if ALPHA_HOOKS in c]
    assert "echo mine" in commands(project)
    assert after["permissions"] == before["permissions"]
    assert hooks_path(project) is None
    assert git(project, "status", "--porcelain") == f"M {SETTINGS}"
    assert git(project, "rev-parse", "HEAD") == head
    assert status(project).name == "hooks-off"
    again = run_cli("uninstall", str(project))
    assert again.returncode == 0 and "already off" in again.stdout


def test_R1_4_hooks_on_restores_what_uninstall_removed(
    project: Path, chained: Path
) -> None:
    original = (project / SETTINGS).read_text()
    assert run_cli("uninstall", str(project)).returncode == 0
    done = run_cli("hooks", "on", str(project))
    assert done.returncode == 0, done.stderr
    assert (project / SETTINGS).read_text() == original
    assert hooks_path(project) == ".claude/alpha/githooks"
    assert git(project, "status", "--porcelain") == ""
    assert status(project).name == "installed"

    assert bad_commit(chained).returncode != 0  # alpha's check runs, chained
    assert run_cli("uninstall", str(chained)).returncode == 0
    assert run_cli("hooks", "on", str(chained)).returncode == 0
    assert (chained / ".husky/commit-msg").read_text() == CHAINED
    assert not (chained / ".claude/alpha/state/chain.json").exists()
    assert bad_commit(chained).returncode != 0


def test_hooks_on_merges_into_settings_changed_since(project: Path) -> None:
    assert run_cli("uninstall", str(project)).returncode == 0
    settings = json.loads((project / SETTINGS).read_text())
    settings["permissions"]["allow"].append("Bash(just *)")
    (project / SETTINGS).write_text(json.dumps(settings, indent=2) + "\n")
    assert run_cli("hooks", "on", str(project)).returncode == 0
    assert (
        "Bash(just *)"
        in json.loads((project / SETTINGS).read_text())["permissions"]["allow"]
    )
    assert any(ALPHA_HOOKS in c for c in commands(project))
    assert "echo mine" in commands(project)
    assert status(project).name == "installed"


def test_R2_2_a_chained_repo_keeps_its_hooks_path(chained: Path) -> None:
    done = run_cli("uninstall", str(chained))
    assert done.returncode == 0, done.stderr
    assert "took alpha's call out of .husky/commit-msg" in done.stdout
    assert hooks_path(chained) == ".husky"
    hook = (chained / ".husky/commit-msg").read_text()
    assert "alpha" not in hook and 'echo "husky runs last"' in hook
    assert bad_commit(chained).returncode == 0
    assert status(chained).name == "hooks-off"


def test_R2_2_an_unmarked_chained_call_is_left_to_the_user(chained: Path) -> None:
    unmarked = "".join(
        line for line in CHAINED.splitlines(keepends=True) if "alpha:" not in line
    )
    (chained / ".husky/commit-msg").write_text(unmarked)
    done = run_cli("uninstall", str(chained))
    assert done.returncode == 0, done.stderr
    assert (
        ".husky/commit-msg:4: it calls it without the # alpha:begin and # alpha:end"
        in (done.stdout)
    )
    assert (chained / ".husky/commit-msg").read_text() == unmarked


def test_a_folder_without_alpha_has_no_hooks_to_switch(tmp_path: Path) -> None:
    done = run_cli("uninstall", str(tmp_path))
    assert done.returncode == 1
    assert "alpha isn't installed in" in done.stderr


def test_R2_2_husky_9_keeps_alphas_call_behind_its_launcher(chained: Path) -> None:
    """husky 9 points core.hooksPath at .husky/_, whose generated commit-msg
    runs .husky/commit-msg, where alpha's call is."""
    launcher = chained / ".husky/_/commit-msg"
    launcher.parent.mkdir()
    launcher.write_text('#!/bin/sh\nset -e\nsh "$(dirname "$0")/../commit-msg" "$1"\n')
    launcher.chmod(0o755)
    git(chained, "config", "core.hooksPath", ".husky/_")  # no survey names it
    assert bad_commit(chained).returncode != 0
    done = run_cli("uninstall", str(chained))
    assert "took alpha's call out of .husky/commit-msg" in done.stdout, done.stdout
    assert bad_commit(chained).returncode == 0
    assert run_cli("hooks", "on", str(chained)).returncode == 0
    assert (chained / ".husky/commit-msg").read_text() == CHAINED
