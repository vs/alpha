from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn, cast

sys.path.insert(0, str(Path(__file__).parent))
import _common

TOOLS = {"Edit", "Write", "MultiEdit"}
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
        pairs = list(cast("list[Any]", edits))
    olds: list[str] = []
    news: list[str] = []
    for pair in pairs:
        if isinstance(pair, dict):
            fields = cast("dict[str, object]", pair)
            o = fields.get("old_string")
            n = fields.get("new_string")
            olds.append(o if isinstance(o, str) else "")
            news.append(n if isinstance(n, str) else "")
    return "\n".join(olds), "\n".join(news)


def edited(tool: str, tool_input: dict[str, Any], current: str) -> str:
    """The whole file as the edit would leave it."""
    if tool == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else ""
    pairs: list[Any] = [tool_input] if tool == "Edit" else []
    edits = tool_input.get("edits")
    if tool == "MultiEdit" and isinstance(edits, list):
        pairs = list(cast("list[Any]", edits))
    text = current
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        fields = cast("dict[str, object]", pair)
        old, new = fields.get("old_string"), fields.get("new_string")
        if isinstance(old, str) and isinstance(new, str) and old:
            text = text.replace(old, new, -1 if fields.get("replace_all") else 1)
    return text


def wiring_problem(rel: str, before: str, after: str) -> str | None:
    """Why an edit of a settings file would switch alpha's hooks off."""
    if not before.strip() and rel == _common.LOCAL_SETTINGS:
        before = "{}"
    if _common.disables_hooks(after) and not _common.disables_hooks(before):
        return f"disableAllHooks in {rel} switches every hook off"
    if rel == _common.SETTINGS:
        was = _common.alpha_hook_entries(before)
        now = _common.alpha_hook_entries(after)
        if was is not None and now != was:
            return f"the edit changes alpha's hook entries in {rel}"
    return None


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
    tool = inp.get("tool_name")
    tool_input: object = inp.get("tool_input")
    if tool not in TOOLS or not isinstance(tool_input, dict):
        sys.exit(0)
    args = cast("dict[str, Any]", tool_input)
    file_path = args.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        sys.exit(0)
    root = _common.project_root(inp, file_path)
    if _common.checkout_of(root.resolve()) is None:
        sys.exit(0)
    principles = _common.load_principles(root) or {}
    rel = _common.rel_to_root(root, file_path)
    if rel is None:
        sys.exit(0)
    glob = _common.protected_glob(rel, principles)
    if glob is not None:
        _common.block(_common.protected_message(rel, glob, principles))
    if rel in (_common.SETTINGS, _common.LOCAL_SETTINGS):
        current = root / rel
        try:
            before = current.read_text() if current.is_file() else ""
        except OSError:
            before = ""
        problem = wiring_problem(rel, before, edited(str(tool), args, before))
        if problem:
            _common.block(
                f"{problem}. Only {_common.UNINSTALL} switches alpha's hooks off; "
                "ask the user to run it if that is what they want."
            )
    if rel == _common.PRINCIPLES:
        ask(
            f"{_common.PRINCIPLES} is the project's single source of truth: every "
            "alpha check reads its principles, commands, globs and protected paths. "
            "Approve only if the user asked for this change."
        )
    comp = _common.component_for(rel, principles)
    name = None if comp is None else str(comp.get("name"))
    if _common.not_code(rel, principles) or not _common.principle_applies(
        principles, "never-weaken-checks", name
    ):
        sys.exit(0)
    old, new = texts(str(tool), args, root / rel)
    found = weakened(old, new)
    if found and not recorded_exception(root, rel):
        _common.block(
            f"This edit weakens a check ({', '.join(found)}) in {rel}. Principle "
            "never-weaken-checks: fix the cause instead. If the check is wrong "
            "here, add a row to CONTRIBUTING.md's Exceptions table naming the "
            f"path {rel}, the rule and why, then retry; the principles-reviewer "
            "checks that reason."
        )
    sys.exit(0)


def recorded_exception(root: Path, rel: str) -> bool:
    return any(e.path == rel for e in _common.exception_rows(root))


if __name__ == "__main__":
    main()
