import json
from pathlib import Path

import pytest
from helpers import old_python

from .conftest import OLD_PYTHON, Project

HOOKS_PATH = ".claude/alpha/githooks"


def start(project: Project, **extra: object):  # noqa: ANN201
    return project.run_hook(
        "session_start.py", {"hook_event_name": "SessionStart", **extra}
    )


def install_shim(project: Project) -> None:
    project.write(f"{HOOKS_PATH}/commit-msg", "#!/bin/sh\n")


def context(out: str) -> str:
    data = json.loads(out)
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    return data["hookSpecificOutput"]["additionalContext"]


def commit(project: Project) -> str:
    project.write("a.txt", "a")
    project.git("add", "a.txt")
    project.git("commit", "-q", "-m", "feat: Add a")
    return project.git("rev-parse", "HEAD").stdout.strip()


def test_warns_when_hooks_path_unset(project: Project) -> None:
    install_shim(project)
    result = start(project)
    assert result.returncode == 0
    text = context(result.stdout)
    assert text.startswith("alpha: ")
    assert f"git config core.hooksPath {HOOKS_PATH}" in text


def test_silent_when_hooks_path_set(project: Project) -> None:
    install_shim(project)
    project.git("config", "core.hooksPath", HOOKS_PATH)
    result = start(project)
    assert result.returncode == 0
    assert result.stdout == ""


def test_no_hooks_path_warning_without_shim(project: Project) -> None:
    assert start(project).stdout == ""


def test_no_hooks_path_warning_without_principles(project: Project) -> None:
    (project.root / "docs" / "principles.toml").unlink()
    install_shim(project)
    assert start(project).stdout == ""


def test_malformed_principles_warns(project: Project) -> None:
    project.write("docs/principles.toml", "not = [valid")
    text = context(start(project).stdout)
    assert "docs/principles.toml is not valid TOML" in text
    assert "git checkout" in text


def test_multiple_warnings_are_combined(project: Project) -> None:
    install_shim(project)
    project.write("docs/principles.toml", "not = [valid")
    text = context(start(project).stdout)
    assert "core.hooksPath" in text
    assert "not valid TOML" in text


def test_records_head_as_baseline_silently(project: Project) -> None:
    sha = commit(project)
    project.git("config", "core.hooksPath", HOOKS_PATH)
    result = start(project, source="resume")
    assert result.stdout == ""
    assert (
        project.root / ".claude/alpha/state/session-base"
    ).read_text().strip() == sha


def baseline(project: Project) -> str:
    return (project.root / ".claude/alpha/state/session-base").read_text().strip()


def commit_b(project: Project) -> str:
    project.write("b.txt", "b")
    project.git("add", "b.txt")
    project.git("commit", "-q", "-m", "feat: Add b")
    return project.git("rev-parse", "HEAD").stdout.strip()


def test_baseline_moves_on_startup(project: Project) -> None:
    commit(project)
    start(project, source="startup")
    head = commit_b(project)
    start(project, source="startup")
    assert baseline(project) == head


@pytest.mark.parametrize("source", ["resume", "compact", "clear"])
def test_baseline_and_counter_kept_within_a_session(
    project: Project, source: str
) -> None:
    first = commit(project)
    start(project, source="startup")
    commit_b(project)
    counter = project.write(".claude/alpha/state/stop-blocks", '{"count": 2}')
    start(project, source=source)
    assert baseline(project) == first
    assert json.loads(Path(counter).read_text()) == {"count": 2}


def test_no_baseline_without_commits(project: Project) -> None:
    start(project)
    assert not (project.root / ".claude/alpha/state/session-base").exists()


def test_resets_stop_blocks_counter(project: Project) -> None:
    counter = project.write(".claude/alpha/state/stop-blocks", '{"count": 2}')
    start(project)
    assert json.loads(Path(counter).read_text()) == {"count": 0}


def test_old_python_warns_that_hooks_are_off(project: Project) -> None:
    result = project.run_hook(
        "session_start.py", {"hook_event_name": "SessionStart"}, python=OLD_PYTHON
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    text = data["hookSpecificOutput"]["additionalContext"]
    assert data["systemMessage"] == text
    assert "alpha needs Python 3.11+ (found 3.9)" in text
    assert "uv python install 3.12" in text
    assert "hooks are off" in text
    assert "git refuses commits" in text


def test_old_python_is_silent_outside_alpha_projects(project: Project) -> None:
    (project.root / "docs" / "principles.toml").unlink()
    result = project.run_hook("session_start.py", {}, python=OLD_PYTHON)
    assert result.returncode == 0 and result.stdout == ""


def test_real_old_python_warns_that_hooks_are_off(project: Project) -> None:
    exe = old_python()
    if exe is None:
        pytest.skip("no python3 older than 3.11 on this machine")
    result = project.run_hook("session_start.py", {}, python=[exe])
    assert result.returncode == 0, result.stderr
    text = json.loads(result.stdout)["systemMessage"]
    assert "alpha needs Python 3.11+ (found 3." in text
