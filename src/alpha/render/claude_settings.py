from typing import Any

from alpha.recipes import RecipeBook

_GIT_ALLOW = [
    "Bash(git status:*)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
    "Bash(git add:*)",
    "Bash(git commit:*)",
]
_DENY = [
    "Bash(git push --force:*)",
    "Bash(git push -f:*)",
    "Bash(rm -rf:*)",
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(**/*.pem)",
    "Read(**/*.key)",
]
_EDIT_TOOLS = "Edit|Write|MultiEdit"
_STOP_TIMEOUT_SECONDS = 1200
_PROMPT_TIMEOUT_SECONDS = 10


def _hook(script: str, timeout: int | None = None) -> dict[str, Any]:
    hook: dict[str, Any] = {
        "type": "command",
        "command": f'python3 "$CLAUDE_PROJECT_DIR"/.claude/alpha/hooks/{script}',
    }
    if timeout is not None:
        hook["timeout"] = timeout
    return hook


def _entry(hook: dict[str, Any], matcher: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {} if matcher is None else {"matcher": matcher}
    entry["hooks"] = [hook]
    return entry


def render_settings(
    principles: dict[str, Any], book: RecipeBook | None = None
) -> dict[str, Any]:
    stacks = {c["stack"] for c in principles["components"]}
    allow = set(_GIT_ALLOW)
    for stack in stacks:
        allow.update((book or RecipeBook()).get(stack).allow)
    return {
        "permissions": {"allow": sorted(allow), "deny": list(_DENY)},
        "hooks": {
            "SessionStart": [_entry(_hook("session_start.py"))],
            "PreToolUse": [
                _entry(_hook("guard_bash.py"), "Bash"),
                _entry(_hook("guard_paths.py"), _EDIT_TOOLS),
            ],
            "PostToolUse": [_entry(_hook("post_edit.py"), _EDIT_TOOLS)],
            "Stop": [_entry(_hook("stop_checks.py", _STOP_TIMEOUT_SECONDS))],
            "SubagentStart": [_entry(_hook("subagent_start.py"))],
            "SubagentStop": [
                _entry(_hook("stop_checks.py", _STOP_TIMEOUT_SECONDS)),
                _entry(_hook("review_record.py"), "principles-reviewer"),
            ],
            "UserPromptSubmit": [
                _entry(_hook("user_prompt.py", _PROMPT_TIMEOUT_SECONDS))
            ],
        },
    }
