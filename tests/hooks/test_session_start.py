import json
from pathlib import Path

from .conftest import Project

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


def test_baseline_updates_on_every_start(project: Project) -> None:
    commit(project)
    start(project, source="startup")
    project.write("b.txt", "b")
    project.git("add", "b.txt")
    project.git("commit", "-q", "-m", "feat: Add b")
    head = project.git("rev-parse", "HEAD").stdout.strip()
    start(project, source="compact")
    assert (
        project.root / ".claude/alpha/state/session-base"
    ).read_text().strip() == head


def test_no_baseline_without_commits(project: Project) -> None:
    start(project)
    assert not (project.root / ".claude/alpha/state/session-base").exists()


def test_resets_stop_blocks_counter(project: Project) -> None:
    counter = project.write(".claude/alpha/state/stop-blocks", '{"count": 2}')
    start(project)
    assert json.loads(Path(counter).read_text()) == {"count": 0}
