import re
from collections.abc import Mapping, Sequence
from typing import cast

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\f": "\\f",
    "\r": "\\r",
}


def _escape(text: str, *, keep_newlines: bool) -> str:
    out: list[str] = []
    for ch in text:
        if ch == "\n":
            out.append("\n" if keep_newlines else "\\n")
        elif ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def _key(key: str) -> str:
    if _BARE_KEY.fullmatch(key):
        return key
    return f'"{_escape(key, keep_newlines=False)}"'


def _path(parts: Sequence[str]) -> str:
    return ".".join(_key(p) for p in parts)


def _string(text: str) -> str:
    if "\n" in text:
        return f'"""\n{_escape(text, keep_newlines=True)}"""'
    return f'"{_escape(text, keep_newlines=False)}"'


def _is_table_array(value: object) -> bool:
    if not isinstance(value, list):
        return False
    items = cast(list[object], value)
    return len(items) > 0 and all(isinstance(v, Mapping) for v in items)


def _value(value: object, where: Sequence[str]) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        items: list[str] = []
        for item in cast(list[object], value):
            if isinstance(item, bool) or not isinstance(item, (str, int)):
                raise TypeError(f"cannot write {type(item)!r} at {'.'.join(where)}")
            items.append(_value(item, where))
        return "[" + ", ".join(items) + "]"
    raise TypeError(f"cannot write {type(value)!r} at {'.'.join(where)}")


def _emit_table(
    data: Mapping[str, object], path: tuple[str, ...], out: list[str]
) -> None:
    subtables: list[tuple[str, Mapping[str, object]]] = []
    table_arrays: list[tuple[str, list[Mapping[str, object]]]] = []
    for key, value in data.items():
        if isinstance(value, Mapping):
            subtables.append((key, cast(Mapping[str, object], value)))
        elif _is_table_array(value):
            table_arrays.append((key, cast(list[Mapping[str, object]], value)))
        else:
            out.append(f"{_key(key)} = {_value(value, (*path, key))}")
    for key, sub in subtables:
        out.append("")
        out.append(f"[{_path((*path, key))}]")
        _emit_table(sub, (*path, key), out)
    for key, items in table_arrays:
        for item in items:
            out.append("")
            out.append(f"[[{_path((*path, key))}]]")
            _emit_table(item, (*path, key), out)


def dumps(data: Mapping[str, object]) -> str:
    out: list[str] = []
    _emit_table(data, (), out)
    return "\n".join(out).lstrip("\n") + "\n"
