"""Minimal block-style YAML writer for CI config; strings are always quoted."""

import json
import re
from collections.abc import Mapping, Sized
from typing import cast

_PLAIN_KEY = re.compile(r"[A-Za-z0-9_-]+")
# YAML 1.1 reads these as booleans, so a bare `on:` key would become `true:`.
_BOOL_WORDS = frozenset({"on", "off", "yes", "no", "true", "false", "y", "n"})


def _key(key: str) -> str:
    if _PLAIN_KEY.fullmatch(key) and key.lower() not in _BOOL_WORDS:
        return key
    return json.dumps(key)


def _is_block(value: object) -> bool:
    return isinstance(value, Mapping | list) and bool(cast("Sized", value))


def _inline(value: object, where: str) -> str:
    """An empty collection or a scalar, written on its key's line."""
    if isinstance(value, Mapping):
        return "{}"
    if isinstance(value, list):
        return "[]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)  # a JSON string is a valid double-quoted YAML one
    raise TypeError(f"cannot write {type(value)!r} at {where}")


def _lines(value: object, indent: int, where: str) -> list[str]:
    pad = " " * indent
    out: list[str] = []
    if isinstance(value, Mapping):
        for key, item in cast("Mapping[str, object]", value).items():
            path = f"{where}.{key}" if where else key
            if _is_block(item):
                out.append(f"{pad}{_key(key)}:")
                out += _lines(item, indent + 2, path)
            else:
                out.append(f"{pad}{_key(key)}: {_inline(item, path)}")
        return out
    for i, item in enumerate(cast("list[object]", value)):
        path = f"{where}[{i}]"
        if _is_block(item):
            inner = _lines(item, indent + 2, path)
            out.append(f"{pad}- {inner[0].lstrip()}")
            out += inner[1:]
        else:
            out.append(f"{pad}- {_inline(item, path)}")
    return out


def dumps(data: Mapping[str, object]) -> str:
    """Serialize ``data`` to block-style YAML, keeping insertion order."""
    if not data:
        return "{}\n"
    return "\n".join(_lines(data, 0, "")) + "\n"
