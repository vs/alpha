"""Field validators for the interview answers; each failure says how to fix it."""

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

NAME = re.compile(r"[a-z][a-z0-9-]*")


class AnswersError(Exception):
    pass


def fail(where: str, problem: str, fix: str) -> AnswersError:
    return AnswersError(f"{where}: {problem}. {fix}")


def join(parent: str, key: str) -> str:
    return f"{parent}.{key}" if parent else key


def obj(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise fail(where, "must be an object", "Write it as a JSON object { ... }")
    return cast(Mapping[str, Any], value)


def as_list(value: object, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise fail(where, "must be a list", "Write it as a JSON list [ ... ]")
    return cast(list[Any], value)


def get(d: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise fail(join(where, key), "is missing", f'Add the "{key}" field')
    return d[key]


def string(d: Mapping[str, Any], key: str, where: str, *, blank: bool = False) -> str:
    v = get(d, key, where)
    if not isinstance(v, str) or (not blank and not v.strip()):
        raise fail(join(where, key), "must be a non-empty string", "Provide text")
    return v


def boolean(d: Mapping[str, Any], key: str, where: str) -> bool:
    v = get(d, key, where)
    if not isinstance(v, bool):
        raise fail(join(where, key), "must be true or false", "Use true or false")
    return v


def pos_int(d: Mapping[str, Any], key: str, where: str) -> int:
    v = get(d, key, where)
    if not isinstance(v, int) or isinstance(v, bool):
        raise fail(join(where, key), "must be a whole number", "Use e.g. 200")
    if v <= 0:
        raise fail(join(where, key), f"is {v}", "Use a number greater than 0")
    return v


def choice(d: Mapping[str, Any], key: str, where: str, options: Sequence[str]) -> str:
    v = get(d, key, where)
    if v not in options:
        raise fail(
            join(where, key),
            f"{v!r} is not allowed",
            f"Use one of: {', '.join(sorted(options))}",
        )
    return v


def strings(d: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    items = as_list(get(d, key, where), join(where, key))
    out: list[str] = []
    for i, item in enumerate(items):
        if not isinstance(item, str):
            raise fail(f"{join(where, key)}[{i}]", "must be a string", "Use text")
        out.append(item)
    return tuple(out)


def unmatchable(path: str) -> bool:
    """A relative path or glob no repository path can match: empty, absolute,
    or with an empty, "." or ".." segment (as in "web/", "./web", "a//b")."""
    return path.startswith("/") or any(
        part in ("", ".", "..") for part in path.split("/")
    )


def relative(value: str, where: str) -> None:
    if not value.strip() or unmatchable(value):
        raise fail(
            where,
            f"{value!r} must be a path or glob relative to the project root",
            'Use e.g. "api/**/routes/**": no leading "/" or "./", no trailing '
            '"/", no ".." or "//"',
        )


def paths(d: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    paths = strings(d, key, where)
    if not paths:
        raise fail(join(where, key), "is empty", "List at least one path or glob")
    for i, path in enumerate(paths):
        relative(path, f"{join(where, key)}[{i}]")
    return paths
