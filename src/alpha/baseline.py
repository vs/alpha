"""How a check's findings read, so a baseline can count them (spec §8b)."""

import importlib.util
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

# The component steps a baseline may hold. format_check is fixed once (plan
# step P1), and setup isn't a check of the code.
BASELINE_STEPS = ("lint", "typecheck", "structure", "test")
NOT_BASELINED = {
    "setup": "setup installs the toolchain; it isn't a check of the code",
    "format_check": "formatting is fixed once, in one commit, instead of baselined",
}
_KEYS = frozenset({"command", "pattern", "json", "file_command"})
_JSON_KEYS = frozenset({"items", "file", "rule", "where"})
_GROUPS = ("file", "rule")

Fail = Callable[[str, str, str], Exception]


@dataclass(frozen=True)
class JsonFindings:
    """Findings in a JSON document. `items` is a dotted path where `*` walks a
    list's items or an object's values; `file` and `rule` are dotted paths in
    an item, or `@N` for the key the N-th `*` walked; `where` keeps the items
    whose field has that value."""

    items: str
    file: str
    rule: str = ""
    where: Mapping[str, str] = field(default_factory=lambda: {})


@dataclass(frozen=True)
class Baseline:
    """A command whose output names each finding's file and rule. Exactly one
    of `pattern` (a regex with `file` and `rule` groups, matched per line) and
    `json` reads it. `file_command` checks one file, with `{file}` in it."""

    command: str
    pattern: str = ""
    json: JsonFindings | None = None
    file_command: str = ""

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {"command": self.command}
        if self.pattern:
            out["pattern"] = self.pattern
        if self.json is not None:
            j: dict[str, Any] = {"items": self.json.items, "file": self.json.file}
            if self.json.rule:
                j["rule"] = self.json.rule
            if self.json.where:
                j["where"] = dict(self.json.where)
            out["json"] = j
        if self.file_command:
            out["file_command"] = self.file_command
        return out


def _text(d: Mapping[str, object], key: str, where: str, fail: Fail) -> str:
    value = d.get(key, "")
    if not isinstance(value, str):
        raise fail(f"{where}.{key}", "must be text", "Write it as a string")
    if "\n" in value or "\r" in value:
        raise fail(f"{where}.{key}", "has a line break", "Write it on one line")
    return value


def _pattern(value: str, where: str, fail: Fail) -> str:
    try:
        compiled = re.compile(value)
    except re.error as e:
        raise fail(
            where, f"isn't a valid regular expression ({e})", "Fix the expression"
        ) from None
    missing = [g for g in _GROUPS if g not in compiled.groupindex]
    if missing:
        raise fail(
            where,
            f"has no {' or '.join(f'(?P<{g}>…)' for g in missing)} group",
            "Name the file and the rule with (?P<file>…) and (?P<rule>…); make a "
            "group optional with (…)? when some findings lack it",
        )
    return value


def _json(value: object, where: str, fail: Fail) -> JsonFindings:
    if not isinstance(value, dict):
        raise fail(
            where,
            "must be an object",
            'Write e.g. {"items": "diagnostics.*", "file": "file", "rule": "rule"}',
        )
    d = cast("dict[str, object]", value)
    extra = sorted(str(k) for k in d if k not in _JSON_KEYS)
    if extra:
        raise fail(
            where,
            f"unknown key {', '.join(extra)}",
            f"Use only: {', '.join(sorted(_JSON_KEYS))}",
        )
    items = _text(d, "items", where, fail)
    path = _text(d, "file", where, fail)
    if not items or not path:
        raise fail(
            where,
            "needs `items` and `file`",
            "Name where the findings are and where each one names its file, e.g. "
            '"items": "diagnostics.*", "file": "file"',
        )
    stars = items.split(".").count("*")
    for key in ("file", "rule"):
        ref = _text(d, key, where, fail)
        if ref.startswith("@") and not (ref[1:].isdigit() and int(ref[1:]) < stars):
            raise fail(
                f"{where}.{key}",
                f"{ref!r} doesn't name one of the {stars} `*` steps in `items`",
                "Use @0 for the key the first `*` walks, @1 for the second",
            )
    raw_where: object = d.get("where", {})
    if not isinstance(raw_where, dict) or not all(
        isinstance(k, str) and isinstance(v, str)
        for k, v in cast("dict[object, object]", raw_where).items()
    ):
        raise fail(
            f"{where}.where",
            "must map field paths to text",
            'Write e.g. {"severity": "error"}',
        )
    return JsonFindings(
        items=items,
        file=path,
        rule=_text(d, "rule", where, fail),
        where=dict(cast("dict[str, str]", raw_where)),
    )


def baseline_from_data(
    value: object, where: str, fail: Fail, *, file_slot: bool = False
) -> Baseline:
    """`file_slot`: the step also checks single files (lint_file), so the
    baseline needs a `file_command`."""
    if not isinstance(value, dict):
        raise fail(
            where,
            "must be an object",
            'Write {"command": "…", "pattern": "(?P<file>…)…(?P<rule>…)"}',
        )
    d = cast("dict[str, object]", value)
    extra = sorted(str(k) for k in d if k not in _KEYS)
    if extra:
        raise fail(
            where,
            f"unknown key {', '.join(extra)}",
            f"Use only: {', '.join(sorted(_KEYS))}",
        )
    command = _text(d, "command", where, fail)
    if not command.strip():
        raise fail(
            f"{where}.command",
            "is missing",
            "Give the check's command with machine-readable output",
        )
    pattern = _text(d, "pattern", where, fail)
    has_json = "json" in d
    if bool(pattern) == has_json:
        raise fail(
            where,
            "needs exactly one of `pattern` and `json`",
            "Read line output with a `pattern`, or JSON output with `json`",
        )
    file_command = _text(d, "file_command", where, fail)
    if file_slot and not file_command:
        raise fail(
            f"{where}.file_command",
            "is missing",
            "The step also checks one file at a time after each edit: give that "
            "command with {file} where the file goes",
        )
    if file_command and "{file}" not in file_command:
        raise fail(
            f"{where}.file_command",
            "doesn't say where the file goes",
            "Put {file} in it",
        )
    if file_command and not file_slot:
        raise fail(
            f"{where}.file_command",
            "is set, but this check never runs on one file",
            "Remove it",
        )
    return Baseline(
        command=command,
        pattern=_pattern(pattern, f"{where}.pattern", fail) if pattern else "",
        json=_json(d["json"], f"{where}.json", fail) if has_json else None,
        file_command=file_command,
    )


RATCHET = Path(__file__).resolve().parents[2] / "project-files/checks/ratchet.py"


def ratchet() -> ModuleType:
    """The ratchet projects get, so the kit reads findings the same way."""
    spec = importlib.util.spec_from_file_location("alpha_ratchet", RATCHET)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def findings(
    baseline: Baseline, stdout: str, stderr: str, root: Path, cwd: Path
) -> list[tuple[str, str, str]]:
    """(file, rule, the output it came from) for each finding; raises
    ValueError when the output can't be read."""
    module = ratchet()
    try:
        found = module.parse(baseline.to_data(), stdout, stderr, root, cwd)
    except module.Unreadable as e:
        raise ValueError(str(e)) from None
    return cast("list[tuple[str, str, str]]", found)
