"""Tool registry: reviewed quality tools with verified pins, and pinned actions."""

import os
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, TypeVar

from alpha.defaults import Source, locate_source
from alpha.validate import AnswersError, fail, get, join, obj, pos_int, string, strings

BUNDLED = Path(__file__).resolve().parents[2]
_TOOLS = "registry/tools.toml"
_ACTIONS = "registry/actions.toml"
_SHA_CHARS = frozenset("0123456789abcdef")

T = TypeVar("T")


class RegistryError(AnswersError):
    """A registry that can't be used; the message names the field and the fix."""


@dataclass(frozen=True)
class Pin:
    """How alpha installs and runs a tool, as verified in a scratch folder."""

    mise: str  # the mise tool spec, e.g. "typos" or "github:betterleaks/betterleaks"
    version: str
    command: str  # the check as a project runs it from its root
    fails_with: int  # the exit code on a violation


@dataclass(frozen=True)
class Tool:
    id: str
    name: str
    repo: str
    category: str
    stacks: tuple[str, ...]  # empty for a cross-cutting tool
    rationale: str
    limitations: str
    last_reviewed: date
    pin: Pin | None


@dataclass(frozen=True)
class Action:
    repo: str
    version: str
    sha: str


class Registry:
    def __init__(self, tools: dict[str, Tool], actions: dict[str, Action]) -> None:
        self._tools = tools
        self._actions = actions

    def tool(self, id: str) -> Tool:
        if id not in self._tools:
            raise RegistryError(
                f"No tool {id!r} in the registry. Run `alpha registry list` "
                "to see the ids."
            )
        return self._tools[id]

    def action(self, repo: str) -> Action:
        if repo not in self._actions:
            raise RegistryError(
                f"No action {repo!r} in the registry. Add it to registry/actions.toml "
                "with its release tag and commit SHA."
            )
        return self._actions[repo]

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def for_stack(self, stack: str) -> list[Tool]:
        """Tools for the stack, then the cross-cutting ones."""
        return [t for t in self._tools.values() if stack in t.stacks or not t.stacks]

    def stale(self, today: date, max_age_days: int = 180) -> list[Tool]:
        limit = timedelta(days=max_age_days)
        return [t for t in self._tools.values() if today - t.last_reviewed > limit]


def _checked(where: str, build: Callable[[], T]) -> T:
    try:
        return build()
    except RegistryError:
        raise
    except AnswersError as e:
        raise RegistryError(str(e), e.where or where) from e


def _day(d: dict[str, Any], key: str, where: str) -> date:
    value = get(d, key, where)
    if type(value) is not date:
        raise fail(
            join(where, key),
            f"is {value!r}, not a date",
            "Write it unquoted as YYYY-MM-DD, e.g. 2026-11-09",
        )
    return value


def _pin(value: object, where: str) -> Pin:
    d = obj(value, where)
    return Pin(
        mise=string(d, "mise", where),
        version=string(d, "version", where),
        command=string(d, "command", where),
        fails_with=pos_int(d, "fails_with", where),
    )


def _tool(id: str, value: object) -> Tool:
    where = join("tools", id)
    d = dict(obj(value, where))
    raw_pin = d.get("pin")
    return Tool(
        id=id,
        name=string(d, "name", where),
        repo=string(d, "repo", where),
        category=string(d, "category", where),
        stacks=strings(d, "stacks", where),
        rationale=string(d, "rationale", where),
        limitations=string(d, "limitations", where),
        last_reviewed=_day(d, "last_reviewed", where),
        pin=None if raw_pin is None else _pin(raw_pin, join(where, "pin")),
    )


def _action(repo: str, value: object) -> Action:
    where = join("actions", repo)
    d = obj(value, where)
    sha = string(d, "sha", where)
    if len(sha) != 40 or not set(sha) <= _SHA_CHARS:
        raise fail(
            join(where, "sha"),
            f"{sha!r} is not a full 40-hex commit SHA",
            "Copy it from `git ls-remote https://github.com/<repo> refs/tags/<tag>`",
        )
    return Action(repo, string(d, "version", where), sha)


def _read(source: Source, name: str) -> dict[str, Any]:
    for root in (source.path, BUNDLED):
        path = root / name
        if path.is_file():
            try:
                return tomllib.loads(path.read_text())
            except tomllib.TOMLDecodeError as e:
                raise RegistryError(
                    f"{path} is not valid TOML ({e}). Fix the syntax it points to."
                ) from e
    raise RegistryError(
        f"{name} is missing from {source.path} and from the plugin. "
        "Restore it from the alpha repository."
    )


def load_registry(source: Source) -> Registry:
    tools_table = _checked(
        "tools", lambda: obj(_read(source, _TOOLS).get("tools", {}), "tools")
    )
    actions_table = _checked(
        "actions", lambda: obj(_read(source, _ACTIONS).get("actions", {}), "actions")
    )
    tools = {
        id: _checked(join("tools", id), lambda id=id, v=v: _tool(id, v))
        for id, v in tools_table.items()
    }
    actions = {
        repo: _checked(join("actions", repo), lambda repo=repo, v=v: _action(repo, v))
        for repo, v in actions_table.items()
    }
    return Registry(tools, actions)


def default_registry() -> Registry:
    """The registry the defaults come from, for callers that weren't handed one."""
    return load_registry(locate_source(BUNDLED, os.environ, Path.home()))
