import json
import os
import tomllib
from pathlib import Path

import pytest
from helpers import generated_repo, git

from alpha.principles import render_principles
from alpha_evals.seeded import (
    REPO_SEEDS,
    check_commands,
    check_hooks,
    check_repo_seeds,
    seed_source_path,
)

from .conftest import snapshot

WEB = "web-ts-plus-python-api"


def test_seed_source_path_avoids_test_globs():
    c = {
        "source_globs": ["api/**/*.py"],
        "test_globs": ["api/tests/**/*.py", "api/**/test_*.py"],
    }
    assert seed_source_path(c) == "api/eval_seed.py"


def test_seed_source_path_at_the_root():
    c = {"source_globs": ["**/*.py"], "test_globs": ["tests/**/*.py"]}
    assert seed_source_path(c) == "eval_seed.py"


def test_seed_source_path_refuses_globs_it_cannot_satisfy():
    c = {"source_globs": ["**/eval_seed*"], "test_globs": ["**/eval_seed*"]}
    with pytest.raises(ValueError):
        seed_source_path(c)


def test_hooks_pass_on_a_fresh_skeleton(tmp_path: Path, git_env, stub_tools):
    project = generated_repo(tmp_path / "p", WEB)
    check = check_hooks(project, tmp_path / "scratch")
    assert check.name == "hooks"
    assert (check.status, check.detail) == ("pass", "")


def test_hooks_fail_when_the_bash_guard_is_unwired(tmp_path: Path, git_env, stub_tools):
    project = generated_repo(tmp_path / "p", WEB)
    path = project / ".claude/settings.json"
    settings = json.loads(path.read_text())
    settings["hooks"]["PreToolUse"] = [
        e for e in settings["hooks"]["PreToolUse"] if e.get("matcher") != "Bash"
    ]
    path.write_text(json.dumps(settings))
    check = check_hooks(project, tmp_path / "scratch")
    assert check.status == "fail"
    assert check.detail.startswith("1. ")
    assert check.detail.count("\n") == 0  # only the no-verify seed failed


def test_hooks_expect_no_untested_flag_where_tests_first_class_is_dropped(
    tmp_path: Path, git_env, stub_tools
):
    project = generated_repo(tmp_path / "p", WEB)
    path = project / "docs/principles.toml"
    data = tomllib.loads(path.read_text())
    for p in data["principles"]:
        if p["id"] == "tests-first-class":
            p["components"] = ["api"]
    path.write_text(render_principles(data))
    check = check_hooks(project, tmp_path / "scratch")
    assert (check.status, check.detail) == ("pass", "")


def test_hooks_leave_the_project_untouched(tmp_path: Path, git_env, stub_tools):
    project = generated_repo(tmp_path / "p", WEB)
    before = snapshot(project)
    check_hooks(project, tmp_path / "scratch")
    assert snapshot(project) == before
    assert git(project, "status", "--porcelain") == ""


def stub_commands(project: Path, **steps: str) -> None:
    path = project / "docs/principles.toml"
    data = tomllib.loads(path.read_text())
    for c in data["components"]:
        for step in c["commands"]:
            c["commands"][step] = "true"
        c["commands"].update(steps)
    path.write_text(render_principles(data))
    git(path.parent.parent, "commit", "-qam", "chore: Stub the checks")


def test_commands_pass_when_every_check_does(tmp_path: Path, git_env):
    project = generated_repo(tmp_path / "p", "python-ml-single")
    stub_commands(project)
    check = check_commands(project)
    assert check.name == "commands"
    assert (check.status, check.detail) == ("pass", "")


def test_commands_report_the_failing_command(tmp_path: Path, git_env):
    project = generated_repo(tmp_path / "p", "python-ml-single")
    stub_commands(project, test="echo boom; false")
    check = check_commands(project)
    assert check.status == "fail"
    assert 'ml: "echo boom; false" failed (exit 1): boom' in check.detail


def test_commands_flag_checks_that_change_files(tmp_path: Path, git_env):
    project = generated_repo(tmp_path / "p", "python-ml-single")
    stub_commands(project, format_check="touch stray.txt")
    check = check_commands(project)
    assert check.status == "fail"
    assert "checks left changes" in check.detail


def test_a_hung_command_times_out(
    tmp_path: Path, git_env, monkeypatch: pytest.MonkeyPatch
):
    from alpha_evals import seeded

    monkeypatch.setattr(seeded, "COMMAND_TIMEOUT", 0.5)
    project = generated_repo(tmp_path / "p", "python-ml-single")
    stub_commands(project, test="sleep 5")
    check = check_commands(project)
    assert check.status == "fail"
    assert 'ml: "sleep 5" timed out after 0.5s' in check.detail


def test_a_hung_hook_times_out(
    tmp_path: Path, git_env, stub_tools, monkeypatch: pytest.MonkeyPatch
):
    from alpha_evals import seeded

    monkeypatch.setattr(seeded, "HOOK_TIMEOUT", 0.5)
    project = generated_repo(tmp_path / "p", "web-ts-plus-python-api")
    path = project / ".claude/settings.json"
    settings = json.loads(path.read_text())
    for entry in settings["hooks"]["PreToolUse"]:
        if entry.get("matcher") == "Bash":
            entry["hooks"][0]["command"] = "sleep 5"
    path.write_text(json.dumps(settings))
    check = check_hooks(project, tmp_path / "scratch")
    assert check.status == "fail"
    assert "1. git commit --no-verify: expected a block, got timed out after 0.5s" in (
        check.detail
    )


def lax_mise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A mise that never fails a check, so no check catches its seed."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    (bin_dir / "mise").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "mise").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")


def test_repo_seeds_pass_when_every_check_fails_on_its_seed(
    tmp_path: Path, git_env, stub_tools
):
    project = generated_repo(tmp_path / "p", WEB)
    check = check_repo_seeds(project)
    assert (check.name, check.status, check.detail) == ("repo-seeds", "pass", "")


def test_repo_seeds_name_a_check_that_misses_its_seed(
    tmp_path: Path, git_env, monkeypatch: pytest.MonkeyPatch
):
    project = generated_repo(tmp_path / "p", WEB)
    lax_mise(tmp_path, monkeypatch)
    check = check_repo_seeds(project)
    assert check.status == "fail"
    for name in REPO_SEEDS:
        assert f"{name}: expected exit" in check.detail


def test_repo_seeds_leave_the_project_untouched(tmp_path: Path, git_env, stub_tools):
    project = generated_repo(tmp_path / "p", WEB)
    before = snapshot(project)
    check_repo_seeds(project)
    assert snapshot(project) == before
    assert git(project, "status", "--porcelain") == ""
