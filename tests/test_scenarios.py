import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
from helpers import git

from alpha.generate import GenerateError
from alpha.gitops import commit_skeleton
from alpha.principles import render_principles

STANDARD_ROOT = {
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CLAUDE.md",
    ".gitignore",
    "docs",
    ".claude",
}
ROOT_ENTRIES = {  # what each scenario may add at the root: its components
    "python-ml-single": STANDARD_ROOT | {"pyproject.toml", "tests"},
    "web-ts-plus-python-api": STANDARD_ROOT | {"api", "web"},
}
SCENARIOS = ["python-ml-single", "web-ts-plus-python-api"]
TRAILER = "Co-Authored-By: T <t@t>"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hook_commands(settings: dict[str, Any]) -> list[str]:
    return [
        hook["command"]
        for entries in settings["hooks"].values()
        for entry in entries
        for hook in entry["hooks"]
    ]


def script_of(command: str) -> str:
    match = re.search(r'"\$CLAUDE_PROJECT_DIR"/(\S+\.py)$', command)
    assert match, command
    return match.group(1)


def git_log_subjects(cwd: Path) -> list[str]:
    return git(cwd, "log", "--format=%s").splitlines()


def principles_of(target: Path) -> dict[str, Any]:
    return tomllib.loads((target / "docs" / "principles.toml").read_text())


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario_skeleton(tmp_path: Path, scenario: str, generate_scenario):
    files = generate_scenario(tmp_path, scenario)
    for f in [
        "CLAUDE.md",
        "docs/principles.toml",
        ".claude/settings.json",
        ".claude/alpha/hooks/stop_checks.py",
        ".claude/skills/commit/SKILL.md",
        ".claude/agents/committer.md",
        ".claude/alpha/githooks/commit-msg",
        ".claude/alpha/project.json",
    ]:
        assert f in files
    assert files == sorted(files)
    assert all((tmp_path / f).is_file() for f in files)
    root_entries = {p.name for p in tmp_path.iterdir()}
    assert root_entries == ROOT_ENTRIES[scenario]  # nothing kit-specific at the root
    assert not any("/src/" in f or f.startswith("src/") for f in files)
    s = json.loads((tmp_path / ".claude/settings.json").read_text())
    for cmd in hook_commands(s):
        assert (tmp_path / script_of(cmd)).is_file()
    m = json.loads((tmp_path / ".claude/alpha/project.json").read_text())["manifest"]
    assert set(m["files"]) == set(files) - {".claude/alpha/project.json"}
    assert all(sha256(tmp_path / p) == h for p, h in m["files"].items())


def test_generated_guard_blocks_no_verify(tmp_path: Path, generate_scenario):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    payload = {"tool_name": "Bash", "tool_input": {"command": "git commit -nm x"}}
    done = subprocess.run(
        [sys.executable, str(tmp_path / ".claude/alpha/hooks/guard_bash.py")],
        cwd=tmp_path,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    assert done.returncode == 2
    assert "--no-verify" in done.stderr


def test_commit_skeleton_groups_and_trailers(
    tmp_path: Path, generate_scenario, git_env
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    hashes = commit_skeleton(tmp_path, principles_of(tmp_path), [TRAILER])
    subjects = git_log_subjects(tmp_path)
    assert subjects == [
        "build(web): Set up typescript toolchain and tests",
        "build(api): Set up python toolchain and tests",
        "chore: Add Claude Code settings and guardrails",
        "docs: Add product brief, principles and decisions",
    ]
    assert hashes == git(tmp_path, "log", "--reverse", "--format=%H").splitlines()
    assert git(tmp_path, "log", "-1", "--format=%B") == (
        f"build(web): Set up typescript toolchain and tests\n\n{TRAILER}"
    )
    assert git(tmp_path, "status", "--porcelain") == ""
    # the commit-msg hook leaves bytecode behind; it must not be committed
    assert (tmp_path / ".claude/alpha/hooks/__pycache__").is_dir()
    assert "__pycache__" not in git(tmp_path, "ls-files")
    assert git(tmp_path, "config", "core.hooksPath") == ".claude/alpha/githooks"
    assert git(tmp_path, "branch", "--show-current") == "main"

    def files_in(commit: str) -> set[str]:
        out = git(tmp_path, "show", "--name-only", "--format=", commit)
        return set(out.splitlines())

    docs, claude, api, web = hashes
    assert {f.split("/")[0] for f in files_in(docs)} == {
        "README.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "docs",
        ".gitignore",
    }
    assert {f.split("/")[0] for f in files_in(claude)} == {"CLAUDE.md", ".claude"}
    assert all(f.startswith("api/") for f in files_in(api))
    assert all(f.startswith("web/") for f in files_in(web))


def test_commit_skeleton_component_at_root_takes_the_rest(
    tmp_path: Path, generate_scenario, git_env
):
    generate_scenario(tmp_path, "python-ml-single")
    commit_skeleton(tmp_path, principles_of(tmp_path), [])
    assert git_log_subjects(tmp_path) == [
        "build(ml): Set up python toolchain and tests",
        "chore: Add Claude Code settings and guardrails",
        "docs: Add product brief, principles and decisions",
    ]
    assert set(git(tmp_path, "show", "--name-only", "--format=", "HEAD").split()) == {
        "pyproject.toml",
        "tests/test_setup.py",
    }
    assert git(tmp_path, "log", "-1", "--format=%B") == (
        "build(ml): Set up python toolchain and tests"
    )
    assert git(tmp_path, "status", "--porcelain") == ""


def test_commit_skeleton_goes_through_the_real_commit_msg_hook(
    tmp_path: Path, generate_scenario, git_env
):
    generate_scenario(tmp_path, "python-ml-single")
    data = principles_of(tmp_path)
    data["git"]["types"] = ["feat"]  # the hook now rejects "docs: ..."
    (tmp_path / "docs" / "principles.toml").write_text(render_principles(data))
    with pytest.raises(GenerateError, match=r'unknown type "docs"') as err:
        commit_skeleton(tmp_path, data, [])
    assert "alpha commit-skeleton" in str(err.value)


def test_commit_skeleton_refuses_a_guessed_git_identity(
    tmp_path: Path, generate_scenario, git_env, monkeypatch: pytest.MonkeyPatch
):
    # No user.name/user.email anywhere: git would otherwise guess one from
    # the login and host name (e.g. you@your-mac.local) and commit with it.
    for var in ("NAME", "EMAIL"):
        for role in ("AUTHOR", "COMMITTER"):
            monkeypatch.delenv(f"GIT_{role}_{var}")
    monkeypatch.delenv("EMAIL", raising=False)
    generate_scenario(tmp_path, "python-ml-single")
    with pytest.raises(GenerateError) as err:
        commit_skeleton(tmp_path, principles_of(tmp_path), [])
    message = str(err.value)
    assert "git config --global user.name" in message
    assert "git config --global user.email" in message
    assert "alpha commit-skeleton" in message
    assert git(tmp_path, "rev-list", "--all") == ""  # nothing committed


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_ds_store_is_never_committed(
    tmp_path: Path, scenario: str, generate_scenario, git_env
):
    (tmp_path / ".DS_Store").write_text("")
    (tmp_path / ".claude" / "alpha").mkdir(parents=True)
    (tmp_path / ".claude" / "alpha" / ".DS_Store").write_text("")
    generate_scenario(tmp_path, scenario)
    commit_skeleton(tmp_path, principles_of(tmp_path), [])
    assert ".DS_Store" not in git(tmp_path, "ls-files")
    assert git(tmp_path, "status", "--porcelain") == ""
