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
        (label, re.compile(r"(?<![\w.$])" + re.escape(label)))
        for label in ("it.skip(", "test.skip(", "describe.skip(", "xit(")
    ]
    + [
        ("except Exception: pass", re.compile(r"except\s+Exception\s*:\s*pass\b")),
        ("except: pass", re.compile(r"except\s*:\s*pass\b")),
    ]
)


def texts(tool: str, tool_input: dict[str, Any], current: Path) -> tuple[str, str]:
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
    glob = _common.protected_glob(rel, principles)
    if glob is not None:
        _common.block(_common.protected_message(rel, glob, principles))
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
    if found and not recorded_exception(root, rel):
        _common.block(
            f"This edit weakens a check ({', '.join(found)}) in {rel}. Principle "
            "never-weaken-checks: fix the cause instead. If the check is wrong "
            "here, record why with the decision skill, naming the path "
            f"{rel} and the rule, then retry; the principles-reviewer checks "
            "that reason."
        )
    sys.exit(0)


def recorded_exception(root: Path, rel: str) -> bool:
    for _n, _title, status, path in _common.decision_index(root)[0]:
        if status != "accepted":
            continue
        try:
            if rel in (root / path).read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeDecodeError):
            continue
    return False


if __name__ == "__main__":
    main()
