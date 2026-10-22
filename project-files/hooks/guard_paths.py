"""PreToolUse hook for Edit|Write|MultiEdit: protects paths, asks on weakened checks."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402

TOOLS = {"Edit", "Write", "MultiEdit"}
PRINCIPLES = "docs/principles.toml"
# (label shown to the user, regex counting its occurrences)
WEAKENING: list[tuple[str, re.Pattern[str]]] = (
    [
        (label, re.compile(re.escape(label)))
        for label in (
            "@pytest.mark.skip",
            "pytest.skip(",
            "@unittest.skip",
            "# type: ignore",
            "# pyright: ignore",
            "# noqa",
            "biome-ignore",
            "eslint-disable",
            "@ts-ignore",
            "@ts-expect-error",
            '"strict": false',
            'typeCheckingMode = "basic"',
            'typeCheckingMode = "off"',
        )
    ]
    + [
        # JS/TS runner calls must be standalone identifiers (not sys.exit(, wait.skip()
        (label, re.compile(r"(?<![\w.$])" + re.escape(label)))
        for label in ("it.skip(", "test.skip(", "describe.skip(", "xit(")
    ]
    + [
        ("except Exception: pass", re.compile(r"except\s+Exception\s*:\s*pass\b")),
        ("except: pass", re.compile(r"except\s*:\s*pass\b")),
    ]
)


def protected_message(rel: str, glob: str, principles: dict[str, Any]) -> str:
    """Why a path is protected (it matched glob), and what to do instead."""
    head = (
        f"{rel} is protected (`{glob}` in docs/principles.toml), so Claude can't "
        "edit it."
    )
    protected = principles.get("protected", {})
    if glob in [str(g) for g in protected.get("extra", [])]:
        return f"{head} Ask the user to change it by hand."
    comp = _common.component_for(rel, principles)
    if comp is not None and rel in [str(p) for p in comp.get("lockfiles", [])]:
        setup = comp.get("commands", {}).get("setup")
        hint = setup if isinstance(setup, str) and setup else "your package manager"
        return (
            f"{head} Lockfiles change only through the package manager (e.g. {hint})."
        )
    return f"{head} Secrets belong in the environment, never in files Claude edits."


def texts(tool: str, tool_input: dict[str, Any], current: Path) -> tuple[str, str]:
    """(old text, new text) for the edit."""
    if tool == "Write":
        try:
            old = current.read_text(errors="replace") if current.is_file() else ""
        except OSError:
            old = ""
        content = tool_input.get("content")
        return old, content if isinstance(content, str) else ""
    pairs: list[Any] = [tool_input] if tool == "Edit" else []
    edits = tool_input.get("edits")
    if tool == "MultiEdit" and isinstance(edits, list):
        pairs = list(edits)  # pyright: ignore[reportUnknownArgumentType]
    olds: list[str] = []
    news: list[str] = []
    for pair in pairs:
        if isinstance(pair, dict):
            o = pair.get("old_string")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            n = pair.get("new_string")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            olds.append(o if isinstance(o, str) else "")
            news.append(n if isinstance(n, str) else "")
    return "\n".join(olds), "\n".join(news)


def weakened(old: str, new: str) -> list[str]:
    return [
        label
        for label, pattern in WEAKENING
        if len(pattern.findall(new)) > len(pattern.findall(old))
    ]


def ask(reason: str) -> NoReturn:
    """Let the user decide on this edit, telling them why."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def main() -> None:
    _common.check_python()
    inp = _common.read_input()
    root = _common.project_root(inp)
    principles = _common.load_principles(root)
    if principles is None:
        sys.exit(0)
    tool = inp.get("tool_name")
    tool_input: object = inp.get("tool_input")
    if tool not in TOOLS or not isinstance(tool_input, dict):
        sys.exit(0)
    args: dict[str, Any] = tool_input  # pyright: ignore[reportUnknownVariableType]
    file_path = args.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        sys.exit(0)
    rel = _common.rel_to_root(root, file_path)
    if rel is None:
        sys.exit(0)
    globs: list[str] = list(principles.get("protected", {}).get("paths", []))
    matched = [g for g in globs if _common.matches(rel, [g])]
    if matched:
        _common.block(protected_message(rel, matched[0], principles))
    if rel == PRINCIPLES:
        ask(
            f"{PRINCIPLES} is the project's single source of truth: every alpha "
            "check reads its principles, commands, globs and protected paths. "
            "Approve only if the user asked for this change."
        )
    comp = _common.component_for(rel, principles)
    name = None if comp is None else str(comp.get("name"))
    if not _common.principle_applies(principles, "never-weaken-checks", name):
        sys.exit(0)
    old, new = texts(str(tool), args, root / rel)
    found = weakened(old, new)
    if found:
        ask(
            f"This edit weakens a check ({', '.join(found)}). Principle "
            "never-weaken-checks: fix the cause instead, or approve if you are sure."
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
