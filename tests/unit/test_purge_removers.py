"""purge's removers, one per kind of kept file (spec, R3.2 and R3.3)."""

import re
import subprocess
from pathlib import Path

import pytest
from helpers import TODAY

from alpha.answers import load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles
from alpha.purge import (
    LISTED_FILES,
    Removed,
    Uncleanable,
    clean_markdown,
    clean_mise,
    clean_settings,
    clean_toml_arrays,
    clean_workflow,
    unratcheted,
    unwrapped_secret_scan,
)
from alpha.render.docs import render_docs

FIXTURE = Path(__file__).parents[1] / "fixtures" / "answers_valid.json"
REMOVED = Removed(
    frozenset({".claude/skills/commit/SKILL.md", ".claude/agents/committer.md"}),
    ("audit", "commit", "decision", "review-change"),
    ("committer", "principles-reviewer"),
)
ALPHA = re.compile(
    r"\.claude/alpha/|docs/alpha/|/alpha:|principles-reviewer|commit skill"
    r"|decision skill|/commit\b"
)


def rendered_claude_md(tmp_path: Path) -> str:
    path = tmp_path / ".claude/alpha/project.json"
    path.parent.mkdir(parents=True)
    path.write_text(FIXTURE.read_text())
    a = load_answers(path)
    defaults = load_defaults(Source(PLUGIN_ROOT, True))
    return render_docs(a, build_principles(defaults, a, "0.1.0"), 2026, TODAY)[
        "CLAUDE.md"
    ]


def test_R3_2_only_alphas_lines_leave_claude_md(tmp_path: Path) -> None:
    mine = "- Ask Dana before touching the billing code."
    text = rendered_claude_md(tmp_path).replace(
        "## Working rules\n\n", f"## Working rules\n\n{mine}\n"
    )
    cleaned = clean_markdown(text, REMOVED)
    assert not [line for line in cleaned.splitlines() if ALPHA.search(line)]
    assert mine in cleaned
    for kept in ("## Principles", "**Fail fast, fail helpfully**", "## Commands"):
        assert kept in cleaned
    assert "| setup |" in cleaned  # the commands table
    lines = cleaned.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#"):
            after = next((x for x in lines[i + 1 :] if x.strip()), None)
            assert after is not None, line
            assert not (
                after.startswith("#")
                and len(after) - len(after.lstrip("#"))
                <= len(line) - len(line.lstrip("#"))
            ), line
    assert "\n\n\n" not in cleaned


def test_an_emptied_code_block_and_check_rows_go() -> None:
    text = (
        "# Contributing\n\n## One-time setup\n\n```sh\n"
        "git config core.hooksPath .claude/alpha/githooks\n```\n\n"
        "Then set up each component.\n\n"
        "| Check | What |\n|---|---|\n| secrets | Secrets |\n| typos | Spelling |\n"
    )
    cleaned = clean_markdown(text, REMOVED, ("secrets",))
    assert "```" not in cleaned and "| secrets |" not in cleaned
    assert "| typos | Spelling |" in cleaned
    assert "## One-time setup\n\nThen set up each component." in cleaned


def test_a_heading_in_a_code_block_is_not_a_heading() -> None:
    text = "# T\n\n## Run\n\n```sh\n# run: add it\n```\n"
    assert clean_markdown(text, REMOVED) == text


def test_tool_config_arrays_lose_only_alphas_entries() -> None:
    text = (
        "[files]\n"
        'extend-exclude = [".claude/alpha/state/", ".env", "CHANGELOG.md"]\n'
        'exclude_path = ["(?:^|/)\\\\.claude/alpha/notes/", "(?:^|/)\\\\.env"]\n'
    )
    assert clean_toml_arrays(text, REMOVED) == (
        "[files]\n"
        'extend-exclude = [".env", "CHANGELOG.md"]\n'
        'exclude_path = ["(?:^|/)\\\\.env"]\n'
    )


MISE = """[tasks]

[tasks."check:typos"]
run = "typos"

[tasks."check:secrets"]
run = "python3 .claude/alpha/checks/secret_scan.py betterleaks dir"

[tasks."check:component:api"]
dir = "api"
run = ["uv sync", "python3 ../.claude/alpha/checks/ratchet.py lint:api"]

[tasks.ci]
depends = ["check:typos", "check:secrets"]
"""


def test_mise_loses_alphas_tasks_and_ratchets() -> None:
    plain = unratcheted(MISE, {"lint:api": "uv run ruff check"}, "mise.toml")
    text, gone = clean_mise(plain, REMOVED)
    assert gone == ["check:secrets"]
    assert 'run = ["uv sync", "uv run ruff check"]' in text
    assert 'depends = ["check:typos"]' in text
    assert "secret_scan" not in text and "\n\n\n" not in text


def test_the_secrets_check_stays_without_alphas_wrapper() -> None:
    text = (
        '[tasks."check:secrets"]\n'
        'run = "python3 .claude/alpha/checks/secret_scan.py betterleaks dir '
        '--no-banner --config .betterleaks.toml"\n'
    )
    plain, gone = clean_mise(unwrapped_secret_scan(text), REMOVED)
    assert gone == []
    assert plain == (
        '[tasks."check:secrets"]\n'
        'run = "git rev-parse --git-dir >/dev/null && '
        "git ls-files -z --cached --others --exclude-standard | xargs -0 -r "
        'betterleaks dir --no-banner --config .betterleaks.toml --"\n'
    )


def test_a_ratchet_alpha_cant_map_back_stops_purge() -> None:
    with pytest.raises(Uncleanable, match="mise.toml: alpha can't put"):
        unratcheted(MISE, {}, "mise.toml")


def test_a_workflow_loses_the_steps_of_removed_tasks() -> None:
    text = (
        "jobs:\n  repo:\n    steps:\n"
        '      - uses: "actions/checkout@abc"\n'
        '      - name: "secrets"\n        run: "mise run check:secrets"\n'
        '      - name: "typos"\n        run: "mise run check:typos"\n'
    )
    assert clean_workflow(text, ["check:secrets"]) == (
        "jobs:\n  repo:\n    steps:\n"
        '      - uses: "actions/checkout@abc"\n'
        '      - name: "typos"\n        run: "mise run check:typos"\n'
    )


def test_settings_lose_alphas_hooks_and_permissions() -> None:
    alphas_stop = {"hooks": [{"command": "python3 .claude/alpha/hooks/stop_checks.py"}]}
    settings: dict[str, object] = {
        "permissions": {"allow": ["Bash(git status)", "Bash(make *)"], "deny": ["X"]},
        "hooks": {"Stop": [alphas_stop, {"hooks": [{"command": "echo mine"}]}]},
        "model": "opus",
    }
    alpha = {"allow": ["Bash(git status)"], "deny": ["X"]}
    assert clean_settings(settings, alpha) == {
        "permissions": {"allow": ["Bash(make *)"]},
        "hooks": {"Stop": [{"hooks": [{"command": "echo mine"}]}]},
        "model": "opus",
    }
    only_alpha: dict[str, object] = {
        "permissions": alpha,
        "hooks": {"Stop": [alphas_stop]},
    }
    assert clean_settings(only_alpha, alpha) == {}


def test_the_chain_marks_are_alphas_lines() -> None:
    text = "# Setup\n\n```sh\n# alpha:begin\nsh x\n# alpha:end\n```\n\nMore.\n"
    assert clean_markdown(text, REMOVED) == "# Setup\n\n```sh\nsh x\n```\n\nMore.\n"


def test_the_secrets_pipeline_fails_when_git_does(tmp_path: Path) -> None:
    """Outside a repository git lists nothing, and xargs -r would run no scan
    at all: the task must fail, not pass."""
    command = LISTED_FILES + "true --"
    done = subprocess.run(["sh", "-c", command], cwd=tmp_path, capture_output=True)
    assert done.returncode != 0
