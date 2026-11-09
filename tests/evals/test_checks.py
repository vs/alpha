import json
import os
from pathlib import Path

import pytest
from helpers import generated_repo, git

from alpha_evals.checks import (
    check_answers,
    check_commits,
    check_files,
    check_repo_checks,
    check_settings,
)
from alpha_evals.scenario import load_brief

WEB = "web-ts-plus-python-api"


def edit_answers(project: Path, change) -> None:
    path = project / ".claude/alpha/project.json"
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def test_a_fresh_skeleton_passes_every_check(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    brief = load_brief(WEB)
    for check in (
        check_answers(project, brief),
        check_files(project),
        check_settings(project),
        check_commits(project),
    ):
        assert check.status == "pass", (check.name, check.detail)
        assert check.detail == ""


def test_answers_names_the_mismatched_pointer(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    edit_answers(project, lambda d: d.update(layout="single"))
    check = check_answers(project, load_brief(WEB))
    assert check.name == "answers"
    assert check.status == "fail"
    assert '/layout: expected "monorepo", got "single"' in check.detail


def test_answers_reports_a_missing_value(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    edit_answers(project, lambda d: d.pop("releases"))
    check = check_answers(project, load_brief(WEB))
    assert '/releases/scheme: expected "semver", got nothing' in check.detail


def test_answers_fails_on_a_pending_area(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    edit_answers(project, lambda d: d["areas"].update(ui="pending"))
    check = check_answers(project, load_brief(WEB))
    assert check.status == "fail"
    assert "area ui is pending" in check.detail


def test_answers_fails_on_unreadable_answers(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    (project / ".claude/alpha/project.json").write_text("{")
    check = check_answers(project, load_brief(WEB))
    assert check.status == "fail"
    assert ".claude/alpha/project.json" in check.detail


def test_files_fails_on_a_missing_hook_script(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    (project / ".claude/alpha/hooks/stop_checks.py").unlink()
    check = check_files(project)
    assert check.status == "fail"
    assert ".claude/alpha/hooks/stop_checks.py" in check.detail


def test_files_fails_on_a_changed_generated_file(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    with (project / "README.md").open("a") as f:
        f.write("more\n")
    check = check_files(project)
    assert check.status == "fail"
    assert "README.md: changed since generation" in check.detail


def test_files_fails_on_app_code_in_src(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    (project / "api/src").mkdir()
    (project / "api/src/main.py").write_text("x = 1\n")
    git(project, "add", "api/src/main.py")
    check = check_files(project)
    assert check.status == "fail"
    assert "api/src/main.py" in check.detail


def test_settings_fails_on_broken_toml(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    (project / "docs/principles.toml").write_text("[[")
    check = check_settings(project)
    assert check.name == "settings"
    assert check.status == "fail"
    assert "docs/principles.toml" in check.detail


def test_settings_fails_on_settings_without_hooks(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    (project / ".claude/settings.json").write_text("{}")
    check = check_settings(project)
    assert check.status == "fail"
    assert ".claude/settings.json" in check.detail


def test_commits_flags_a_message_the_hook_rejects(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    (project / "x.txt").write_text("x\n")
    git(project, "add", "x.txt")
    git(project, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "added stuff")
    check = check_commits(project)
    assert check.name == "commits"
    assert check.status == "fail"
    assert "added stuff" in check.detail


def test_commits_flags_a_dirty_tree(tmp_path: Path, git_env):
    project = generated_repo(tmp_path, WEB)
    (project / "stray.txt").write_text("x\n")
    check = check_commits(project)
    assert check.status == "fail"
    assert "uncommitted" in check.detail


def test_commits_fails_without_any_commit(tmp_path: Path, git_env):
    git(tmp_path, "init", "-q", "-b", "main")
    check = check_commits(tmp_path)
    assert check.status == "fail"
    assert "no commits" in check.detail


def test_check_to_json():
    from alpha_evals.checks import Check

    assert Check("files", "pass").to_json() == {
        "name": "files",
        "status": "pass",
        "detail": "",
    }


def fake_mise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    script = bin_dir / "mise"
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")


def test_repo_checks_check_passes_when_mise_run_ci_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fake_mise(tmp_path, monkeypatch, 'test "$*" = "run ci"')
    check = check_repo_checks(tmp_path)
    assert (check.name, check.status, check.detail) == ("repo-checks", "pass", "")


def test_repo_checks_check_reports_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fake_mise(tmp_path, monkeypatch, "echo 'typos: teh in README.md'; exit 1")
    check = check_repo_checks(tmp_path)
    assert check.name == "repo-checks"
    assert check.status == "fail"
    assert "mise run ci failed (exit 1)" in check.detail
    assert "typos: teh in README.md" in check.detail


def test_repo_checks_check_says_when_mise_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PATH", str(tmp_path))
    check = check_repo_checks(tmp_path)
    assert check.status == "fail"
    assert "mise is not installed" in check.detail
