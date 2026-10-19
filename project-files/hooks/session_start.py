"""SessionStart hook: setup warnings, session baseline, stop-counter reset."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402

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
    import tomllib  # lazy: absent on 3.9, and check_python() has exited by then

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


def main() -> None:
    _common.check_python()
    inp = _common.read_input()
    root = _common.project_root(inp)
    principles = root / "docs" / "principles.toml"
    if not principles.is_file():
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
    head = git_out(root, "rev-parse", "--verify", "-q", "HEAD")
    if head:
        _common.write_baseline(root, head)
    _common.state_path(root, "stop-blocks").write_text(json.dumps({"count": 0}))
    if warnings:
        text = "alpha: " + " ".join(warnings)
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": text,
                    }
                }
            )
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
