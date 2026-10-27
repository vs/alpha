"""SessionStart hook: the decision index, setup warnings, a new Stop baseline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402
import review  # noqa: E402

HOOKS_PATH = ".claude/alpha/githooks"


def git_out(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def principles_problem(path: Path) -> str | None:
    import tomllib  # lazy: absent on 3.9, and main() has returned by then

    try:
        with path.open("rb") as f:
            tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        return (
            f"docs/principles.toml is not valid TOML: {e}. Fix the file (it is the "
            "single source of truth for alpha's checks), or restore it with "
            '"git checkout docs/principles.toml".'
        )
    except OSError as e:
        return f"docs/principles.toml is unreadable: {e}. Check its permissions."
    return None


def old_python_warning(problem: str) -> None:
    """Tell the user and Claude that the hooks are off; must run on Python 3.9."""
    text = (
        f"alpha: the project's hooks are off. {problem} Until then git refuses "
        "commits and nothing checks protected files or work before stopping; "
        "restart the session once python3 is 3.11+."
    )
    print(
        json.dumps(
            {
                "systemMessage": text,
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": text,
                },
            }
        )
    )


def main() -> None:
    inp = _common.read_input()
    root = _common.project_root(inp)
    principles = root / "docs" / "principles.toml"
    if not principles.is_file():
        sys.exit(0)
    problem = _common.python_problem()
    if problem:
        old_python_warning(problem)
        sys.exit(0)
    warnings: list[str] = []
    if (root / HOOKS_PATH / "commit-msg").is_file():
        if git_out(root, "config", "core.hooksPath") != HOOKS_PATH:
            warnings.append(
                f"commit hook not active. Run: git config core.hooksPath {HOOKS_PATH}"
            )
    problem = principles_problem(principles)
    if problem:
        warnings.append(problem)
    # A new session starts a new baseline. Resume, compact and clear continue
    # the same work, so commits made earlier in it are still checked at Stop.
    if inp.get("source") == "startup":
        # Subagents of an earlier session are gone; what they left is stale.
        for stale in (root / _common.STATE_DIR).glob("agent-*"):
            stale.unlink(missing_ok=True)
    if inp.get("source") == "startup" or _common.read_baseline(root) is None:
        head = git_out(root, "rev-parse", "--verify", "-q", "HEAD")
        if head:
            _common.write_baseline(root, head)
            # Unlike the baseline, this stays put for the whole session.
            _common.state_path(root, "session-start").write_text(head + "\n")
        _common.state_path(root, "stop-blocks").write_text(json.dumps({"count": 0}))
    parts: list[str] = []
    if problem is None:
        state = review.ensure_state(root)
        notice = state.pop("notice", None)
        if notice:
            parts.append(str(notice))
            review.save_state(root, state)
    if problem is None:  # principles parse, so the index can name overrides
        loaded = _common.load_principles(root)
        if loaded is not None:
            parts.append(_common.context_text(root, loaded))
    if warnings:
        parts.append("alpha: " + " ".join(warnings))
    if parts:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": "\n\n".join(parts),
                    }
                }
            )
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
