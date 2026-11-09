import json
import re
from collections.abc import Mapping, Sized
from typing import cast

# Starting with a letter keeps numbers (1, 0x1f) and list dashes out.
_PLAIN_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
# YAML 1.1 reads these as booleans or null, so a bare `on:` key would become
# `true:`.
_NOT_STRINGS = frozenset({"on", "off", "yes", "no", "true", "false", "y", "n", "null"})
# What YAML keeps as written in a double-quoted string: printable characters
# other than line breaks (NEL and the Unicode separators fold into spaces).
_UNPRINTABLE = re.compile(
    "[^\t\n\r\x20-\x7e\xa0-\u2027\u202a-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]"
)


def _quoted(text: str) -> str:
    """A double-quoted YAML string; a JSON string is one, once characters
    outside the BMP are written as themselves instead of surrogate pairs."""
    body = json.dumps(text, ensure_ascii=False)
    return _UNPRINTABLE.sub(lambda m: f"\\u{ord(m.group()):04x}", body)


def _key(key: str) -> str:
    if _PLAIN_KEY.fullmatch(key) and key.lower() not in _NOT_STRINGS:
        return key
    return _quoted(key)


def _is_block(value: object) -> bool:
    return isinstance(value, Mapping | list) and bool(cast("Sized", value))


def _inline(value: object, where: str) -> str:
    if isinstance(value, Mapping):
        return "{}"
    if isinstance(value, list):
        return "[]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _quoted(value)
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
    if not data:
        return "{}\n"
    return "\n".join(_lines(data, 0, "")) + "\n"
