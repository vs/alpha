import re
from pathlib import Path
from typing import Any

from alpha.answers import load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles
from alpha.render.claude_settings import render_settings

FIXTURE = Path(__file__).parents[1] / "fixtures" / "answers_valid.json"
HOOKS_DIR = Path(__file__).resolve().parents[2] / "project-files" / "hooks"
PRINCIPLES = build_principles(
    load_defaults(Source(PLUGIN_ROOT, True)), load_answers(FIXTURE), "0.0.0"
)
SETTINGS = render_settings(PRINCIPLES)


def entries(event: str) -> list[dict[str, Any]]:
    return SETTINGS["hooks"][event]


def test_allow_covers_the_mise_checks():
    # CLAUDE.md tells Claude to run `mise run check`.
    assert "Bash(mise run:*)" in SETTINGS["permissions"]["allow"]
    # agnix flags a wildcarded interpreter, and auto mode drops it anyway.
    assert not any("python3" in rule for rule in SETTINGS["permissions"]["allow"])


def test_allow_covers_both_stacks_and_git_sorted():
    allow = SETTINGS["permissions"]["allow"]
    assert "Bash(uv run:*)" in allow
    assert "Bash(pnpm vitest:*)" in allow
    assert "Bash(git commit:*)" in allow
    assert allow == sorted(set(allow))


def test_deny_list_exact():
    assert SETTINGS["permissions"]["deny"] == [
        "Bash(git push --force:*)",
        "Bash(git push -f:*)",
        "Bash(rm -rf:*)",
        "Read(**/.env)",
        "Read(**/.env.*)",
        "Read(**/*.pem)",
        "Read(**/*.key)",
    ]


def test_key_order_is_deterministic():
    assert list(SETTINGS) == ["permissions", "hooks"]
    assert list(SETTINGS["permissions"]) == ["allow", "deny"]
    assert list(SETTINGS["hooks"]) == [
        "SessionStart",
        "PreToolUse",
        "PostToolUse",
        "Stop",
        "SubagentStart",
        "SubagentStop",
        "UserPromptSubmit",
    ]


def test_hook_wiring():
    def cmd(script: str) -> dict[str, str]:
        return {
            "type": "command",
            "command": f'python3 "$CLAUDE_PROJECT_DIR"/.claude/alpha/hooks/{script}',
        }

    assert entries("SessionStart") == [{"hooks": [cmd("session_start.py")]}]
    assert entries("PreToolUse") == [
        {"matcher": "Bash", "hooks": [cmd("guard_bash.py")]},
        {"matcher": "Edit|Write|MultiEdit", "hooks": [cmd("guard_paths.py")]},
    ]
    assert entries("PostToolUse") == [
        {"matcher": "Edit|Write|MultiEdit", "hooks": [cmd("post_edit.py")]}
    ]
    assert entries("Stop") == [{"hooks": [{**cmd("stop_checks.py"), "timeout": 1200}]}]
    assert entries("SubagentStart") == [{"hooks": [cmd("subagent_start.py")]}]
    assert entries("SubagentStop") == [
        {"hooks": [{**cmd("stop_checks.py"), "timeout": 1200}]},
        {"matcher": "principles-reviewer", "hooks": [cmd("review_record.py")]},
    ]
    assert entries("UserPromptSubmit") == [
        {"hooks": [{**cmd("user_prompt.py"), "timeout": 10}]}
    ]


def test_every_hook_command_names_an_existing_script():
    commands = [
        h["command"]
        for group in SETTINGS["hooks"].values()
        for entry in group
        for h in entry["hooks"]
    ]
    assert len(commands) == 9
    for command in commands:
        match = re.search(r"/([a-z_]+\.py)$", command)
        assert match, command
        assert (HOOKS_DIR / match.group(1)).is_file()
