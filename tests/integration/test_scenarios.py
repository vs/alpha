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
from helpers import TODAY, GenerateScenario, git, place_answers

from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import GenerateError, generate
from alpha.gitops import commit_skeleton
from alpha.principles import render_principles


@pytest.fixture(autouse=True)
def isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hooks take machine-wide slots under HOME; keep them off the real one."""
    real = Path.home() / ".gitconfig"
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    if "GIT_CONFIG_GLOBAL" not in os.environ and real.is_file():
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(real))


STANDARD_ROOT = {
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CLAUDE.md",
    ".gitignore",
    "docs",
    ".claude",
    # the repository checks' toolchain and the configs of the tools it pins
    "mise.toml",
    "_typos.toml",
    ".rumdl.toml",
    "lychee.toml",
    ".betterleaks.toml",
}
ROOT_ENTRIES = {
    "python-ml-single": STANDARD_ROOT
    | {"pyproject.toml", "tests", ".python-version", ".github"},
    "web-ts-plus-python-api": STANDARD_ROOT | {"api", "web", ".github", "CHANGELOG.md"},
    "rust-cli": STANDARD_ROOT
    | {"Cargo.toml", "clippy.toml", "rust-toolchain.toml", "tests", ".github"},
}
SCENARIOS = ["python-ml-single", "web-ts-plus-python-api", "rust-cli"]
TRAILER = "Co-Authored-By: T <t@t>"


def sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


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
def test_scenario_skeleton(
    tmp_path: Path, scenario: str, generate_scenario: GenerateScenario
):
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
    assert root_entries == ROOT_ENTRIES[scenario]
    assert not any("/src/" in f or f.startswith("src/") for f in files)
    s = json.loads((tmp_path / ".claude/settings.json").read_text())
    for cmd in hook_commands(s):
        assert (tmp_path / script_of(cmd)).is_file()
    m = json.loads((tmp_path / ".claude/alpha/project.json").read_text())["manifest"]
    assert set(m["files"]) == set(files) - {".claude/alpha/project.json"}
    assert all(sha256(tmp_path / p) == h for p, h in m["files"].items())


def test_generated_guard_blocks_no_verify(
    tmp_path: Path, generate_scenario: GenerateScenario
):
    """R3: skipping git hooks in a generated project is blocked."""
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
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    hashes = commit_skeleton(tmp_path, principles_of(tmp_path), [TRAILER])
    subjects = git_log_subjects(tmp_path)
    assert subjects == [
        "ci: Schedule dependency updates",
        "ci: Run every component's checks in CI",
        "build(web): Set up typescript toolchain and tests",
        "build(api): Set up python toolchain and tests",
        "build: Pin the repository's check tools",
        "chore: Add Claude Code settings and guardrails",
        "docs: Add product brief, principles and decisions",
    ]
    assert hashes == git(tmp_path, "log", "--reverse", "--format=%H").splitlines()
    assert git(tmp_path, "log", "-1", "--format=%B") == (
        f"ci: Schedule dependency updates\n\n{TRAILER}"
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

    docs, claude, tooling, api, web, ci, deps = hashes
    assert {f.split("/")[0] for f in files_in(docs)} == {
        "README.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "docs",
        ".gitignore",
    }
    assert files_in(tooling) == {
        "mise.toml",
        "_typos.toml",
        ".rumdl.toml",
        "lychee.toml",
        ".betterleaks.toml",
    }
    assert {f.split("/")[0] for f in files_in(claude)} == {"CLAUDE.md", ".claude"}
    assert all(f.startswith("api/") for f in files_in(api))
    assert all(f.startswith("web/") for f in files_in(web))
    assert files_in(ci) == {
        ".github/jactionlint.yaml",
        ".github/workflows/ci.yml",
        ".github/workflows/scheduled.yml",
    }
    assert files_in(deps) == {".github/dependabot.yml"}


def test_commit_skeleton_component_at_root_takes_the_rest(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "python-ml-single")
    commit_skeleton(tmp_path, principles_of(tmp_path), [])
    assert git_log_subjects(tmp_path) == [
        "ci: Schedule dependency updates",
        "ci: Run every component's checks in CI",
        "build(ml): Set up python toolchain and tests",
        "build: Pin the repository's check tools",
        "chore: Add Claude Code settings and guardrails",
        "docs: Add product brief, principles and decisions",
    ]
    assert set(git(tmp_path, "show", "--name-only", "--format=", "HEAD~2").split()) == {
        "pyproject.toml",
        "tests/test_setup.py",
        ".python-version",
    }
    assert git(tmp_path, "log", "-1", "--format=%B", "HEAD~2") == (
        "build(ml): Set up python toolchain and tests"
    )
    assert git(tmp_path, "status", "--porcelain") == ""


def test_commit_skeleton_goes_through_the_real_commit_msg_hook(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "python-ml-single")
    data = principles_of(tmp_path)
    data["git"]["types"] = ["feat"]
    (tmp_path / "docs" / "principles.toml").write_text(render_principles(data))
    with pytest.raises(GenerateError, match=r'unknown type "docs"') as err:
        commit_skeleton(tmp_path, data, [])
    assert "alpha commit-skeleton" in str(err.value)


def test_commit_skeleton_leaves_out_scopes_not_on_the_list(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    data = principles_of(tmp_path)
    data["git"]["scopes"] = ["backend", "web"]
    (tmp_path / "docs" / "principles.toml").write_text(render_principles(data))
    commit_skeleton(tmp_path, data, [])
    assert git_log_subjects(tmp_path) == [
        "ci: Schedule dependency updates",
        "ci: Run every component's checks in CI",
        "build(web): Set up typescript toolchain and tests",
        "build: Set up api toolchain and tests",
        "build: Pin the repository's check tools",
        "chore: Add Claude Code settings and guardrails",
        "docs: Add product brief, principles and decisions",
    ]
    assert git(tmp_path, "status", "--porcelain") == ""


def test_commit_skeleton_rerun_finishes_after_a_partial_failure(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "python-ml-single")
    data = principles_of(tmp_path)
    data["git"]["types"] = ["docs", "chore"]
    principles = tmp_path / "docs" / "principles.toml"
    principles.write_text(render_principles(data))
    with pytest.raises(GenerateError, match=r'unknown type "build"'):
        commit_skeleton(tmp_path, data, [])
    assert len(git_log_subjects(tmp_path)) == 2
    data["git"]["types"] += ["build", "ci"]
    principles.write_text(render_principles(data))
    commit_skeleton(tmp_path, data, [])
    assert git_log_subjects(tmp_path)[:3] == [
        "ci: Schedule dependency updates",
        "ci: Run every component's checks in CI",
        "build(ml): Set up python toolchain and tests",
    ]
    assert git(tmp_path, "status", "--porcelain") == ""


def test_commit_skeleton_refuses_a_guessed_git_identity(
    tmp_path: Path,
    generate_scenario: GenerateScenario,
    git_env: None,
    monkeypatch: pytest.MonkeyPatch,
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
    assert git(tmp_path, "rev-list", "--all") == ""


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_ds_store_is_never_committed(
    tmp_path: Path, scenario: str, generate_scenario: GenerateScenario, git_env: None
):
    (tmp_path / ".DS_Store").write_text("")
    (tmp_path / ".claude" / "alpha").mkdir(parents=True)
    (tmp_path / ".claude" / "alpha" / ".DS_Store").write_text("")
    generate_scenario(tmp_path, scenario)
    commit_skeleton(tmp_path, principles_of(tmp_path), [])
    assert ".DS_Store" not in git(tmp_path, "ls-files")
    assert git(tmp_path, "status", "--porcelain") == ""


def settings_hook(settings: dict[str, Any], event: str, matcher: str | None) -> str:
    for entry in settings["hooks"][event]:
        if entry.get("matcher") == matcher:
            return entry["hooks"][0]["command"]
    raise KeyError(f"no {event} hook for {matcher!r}")


def test_generated_hooks_enforce_the_generated_principles(
    tmp_path: Path, git_env: None, monkeypatch: pytest.MonkeyPatch
):
    """R3: the generated hooks block what the principles forbid, naming the fix."""
    target = tmp_path / "proj"
    answers = place_answers(target, "web-ts-plus-python-api")
    data = json.loads(answers.read_text())
    data["overrides"].append(
        {
            "principle": "tests-first-class",
            "scope": "component:web",
            "change": "drop",
            "reason": "The web UI is a throwaway prototype for the demo.",
        }
    )
    answers.write_text(json.dumps(data))
    generate(target, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), 2026, TODAY)
    commit_skeleton(target, principles_of(target), [])

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "tools.log"
    for tool in ("uv", "pnpm"):
        script = bin_dir / tool
        script.write_text(f'#!/bin/sh\necho "$(basename "$PWD"): {tool} $*" >> {log}\n')
        script.chmod(0o755)
    (bin_dir / "python3").symlink_to(sys.executable)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(target))
    settings = json.loads((target / ".claude/settings.json").read_text())

    def hook(event: str, matcher: str | None, payload: dict[str, Any]):
        return subprocess.run(
            settings_hook(settings, event, matcher),
            shell=True,
            cwd=target,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )

    started = hook("SessionStart", None, {"source": "startup"})
    assert started.returncode == 0, started.stderr
    told = json.loads(started.stdout)["hookSpecificOutput"]["additionalContext"]
    assert told.startswith("alpha: decisions in effect")
    assert "0001 Product identity [accepted]" in told
    assert "- tests-first-class: drop, scope component:web (" in told

    edit: dict[str, Any] = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(target / "x")},
    }
    for rel in ("api/main.py", "web/app/page.tsx"):
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        (target / rel).write_text("x\n")
        edit["tool_input"]["file_path"] = str(target / rel)
        assert hook("PostToolUse", "Edit|Write|MultiEdit", edit).returncode == 0
    assert log.read_text().splitlines() == [
        "api: uv run ruff format main.py",
        "api: uv run ruff check main.py",
        "web: pnpm biome format --write app/page.tsx",
        "web: pnpm biome lint --error-on-warnings app/page.tsx",
    ]

    stop = hook("Stop", None, {"stop_hook_active": False})
    assert stop.returncode == 0, stop.stderr
    reason = json.loads(stop.stdout)["reason"]
    assert "api: source changed (api/main.py) but no tests changed." in reason
    assert "web: source changed" not in reason
    ran = log.read_text().splitlines()[4:]
    assert ran == [
        "api: uv run pyright",
        "api: uv run deptry .",
        "web: pnpm tsc --noEmit",
        "web: pnpm knip",
        "web: pnpm depcruise --config .dependency-cruiser.cjs .",
    ]
    tests = subprocess.run(
        "python3 .claude/alpha/hooks/stop_checks.py tests",
        shell=True,
        cwd=target,
        capture_output=True,
        text=True,
    )
    assert tests.returncode == 0, tests.stderr
    assert log.read_text().splitlines()[9:] == [
        "api: uv run pytest",
        "web: pnpm vitest run",
    ]

    weaken = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(target / "web/app/page.tsx"),
            "old_string": "x",
            "new_string": "// @ts-ignore\nx",
        },
    }
    weakened = hook("PreToolUse", "Edit|Write|MultiEdit", weaken)
    assert weakened.returncode == 2
    assert "never-weaken-checks" in weakened.stderr
    env_write = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(target / "api/.env")},
    }
    assert hook("PreToolUse", "Edit|Write|MultiEdit", env_write).returncode == 2
    no_verify = {"tool_name": "Bash", "tool_input": {"command": "git commit -nm x"}}
    assert hook("PreToolUse", "Bash", no_verify).returncode == 2


def test_commit_skeleton_commits_ci_last(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    commit_skeleton(tmp_path, principles_of(tmp_path), [])
    assert git_log_subjects(tmp_path)[:2] == [
        "ci: Schedule dependency updates",
        "ci: Run every component's checks in CI",
    ]
    assert git(tmp_path, "show", "--name-only", "--format=", "HEAD").split() == [
        ".github/dependabot.yml"
    ]
    assert git(tmp_path, "show", "--name-only", "--format=", "HEAD~").split() == [
        ".github/jactionlint.yaml",
        ".github/workflows/ci.yml",
        ".github/workflows/scheduled.yml",
    ]
    assert git(tmp_path, "status", "--porcelain") == ""
