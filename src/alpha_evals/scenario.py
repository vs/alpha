"""Scenario briefs for the simulated user, and comparison of the answers."""

import json
import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from alpha.cli import PLUGIN_ROOT

SCENARIOS: tuple[str, ...] = ("python-ml-single", "web-ts-plus-python-api", "rust-cli")
_SELECTOR = re.compile(r"^(\w+)\[(\w+)=([^\]]*)\]$")


class ScenarioError(Exception):
    pass


@dataclass(frozen=True)
class Brief:
    name: str
    text: str
    expect: tuple[str, ...]
    answers: dict[str, Any]


@dataclass(frozen=True)
class Mismatch:
    pointer: str
    expected: Any
    actual: Any | None
    missing: bool


def load_brief(name: str, root: Path = PLUGIN_ROOT) -> Brief:
    """The brief in evals/briefs/<name>.toml, with evals/scenarios/<name>.json."""
    rel = f"evals/briefs/{name}.toml"
    try:
        data = tomllib.loads((root / rel).read_text(encoding="utf-8"))
    except OSError:
        raise ScenarioError(
            f"{rel} not found (scenarios: {', '.join(SCENARIOS)})"
        ) from None
    except tomllib.TOMLDecodeError as e:
        raise ScenarioError(f"{rel} is not valid TOML ({e})") from None
    text = data.get("brief")
    expect = data.get("expect")
    if not isinstance(text, str) or not text.strip():
        raise ScenarioError(f"{rel} needs a non-empty brief string")
    if not isinstance(expect, list) or not all(
        isinstance(p, str) for p in cast(list[Any], expect)
    ):
        raise ScenarioError(f"{rel} needs an expect list of pointers")
    answers_rel = f"evals/scenarios/{name}.json"
    try:
        answers = json.loads((root / answers_rel).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ScenarioError(f"{answers_rel} can't be read ({e})") from None
    return Brief(name, text, tuple(cast(list[str], expect)), answers)


def _step(node: Any, segment: str, pointer: str) -> Any:
    match = _SELECTOR.match(segment)
    if match:
        key, field, value = match.groups()
        items = _step(node, key, pointer)
        if isinstance(items, list):
            for item in cast(list[Any], items):
                if not isinstance(item, dict):
                    continue
                entry = cast(dict[str, Any], item)
                if str(entry.get(field)) == value:
                    return entry
        raise KeyError(pointer)
    if isinstance(node, dict) and segment in node:
        return cast(dict[str, Any], node)[segment]
    if isinstance(node, list) and segment.isdigit():
        items = cast(list[Any], node)
        if int(segment) < len(items):
            return items[int(segment)]
    raise KeyError(pointer)


def resolve(data: Any, pointer: str) -> Any:
    """The value at a pointer like /components[name=api]/stack (~ ignored)."""
    node = data
    for segment in pointer.removeprefix("~").strip("/").split("/"):
        node = _step(node, segment, pointer)
    return node


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        la, lb = cast(list[Any], a), cast(list[Any], b)
        if all(isinstance(x, str) for x in [*la, *lb]):
            return sorted(la) == sorted(lb)
    return a == b


def compare(
    expected: dict[str, Any], actual: dict[str, Any], pointers: Sequence[str]
) -> list[Mismatch]:
    out: list[Mismatch] = []
    for pointer in pointers:
        # "~/a/b": free text, so the answer only has to contain the value.
        loose = pointer.startswith("~")
        path = pointer.removeprefix("~")
        want = resolve(expected, path)
        try:
            got = resolve(actual, path)
        except KeyError:
            out.append(Mismatch(pointer, want, None, True))
            continue
        if loose and isinstance(want, str) and isinstance(got, str):
            if want.lower() not in got.lower():
                out.append(Mismatch(pointer, want, got, False))
        elif not _same(want, got):
            out.append(Mismatch(pointer, want, got, False))
    return out
