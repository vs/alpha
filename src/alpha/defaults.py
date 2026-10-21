"""Kit defaults: catalog, override layering, live source, change recording."""

import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

from alpha import toml_write

CONDITIONS: frozenset[str] = frozenset(
    {
        "always",
        "has_ui",
        "multi_component",
        "communicating_components",
        "deployed",
        "network_calls",
        "persisted_data",
        "ml",
        "nontrivial_logic",
        "budgets_set",
        "domain_jargon",
    }
)

_DEFAULTS = "defaults/defaults.toml"
_OVERRIDES = "defaults/overrides.toml"
_CHANGELOG = "defaults/CHANGELOG.md"
_OVERRIDES_HEADER = '# Managed by "alpha defaults set". Do not edit by hand.\n'


class DefaultsError(Exception):
    pass


class SourceNotLive(DefaultsError):
    """Only the bundled defaults are available, so nothing can be saved."""


@dataclass(frozen=True)
class Source:
    path: Path
    live: bool
    reason: str


def locate_source(plugin_root: Path, env: Mapping[str, str], home: Path) -> Source:
    candidates: list[Path] = []
    if env.get("ALPHA_SOURCE"):
        candidates.append(Path(env["ALPHA_SOURCE"]))
    config = home / ".config/alpha/config.toml"
    if config.is_file():
        try:
            configured = tomllib.loads(config.read_text()).get("source")
        except tomllib.TOMLDecodeError as e:
            raise DefaultsError(
                f"{config} is not valid TOML ({e}). "
                'Fix it so it reads source = "/path/to/alpha".'
            ) from e
        if isinstance(configured, str):
            candidates.append(Path(configured))
    candidates.append(home / "workspace/alpha")
    for candidate in candidates:
        if (candidate / _DEFAULTS).is_file():
            return Source(candidate, True, "")
    tried = ", ".join(str(c) for c in candidates)
    return Source(
        plugin_root,
        False,
        f"no alpha source checkout found (tried {tried}). "
        'Set ALPHA_SOURCE to your alpha checkout, or add source = "/path/to/alpha" '
        f"to {config}.",
    )


def _merge(base: dict[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in over.items():
        current = base.get(key)
        if isinstance(value, Mapping) and isinstance(current, dict):
            _merge(current, value)  # pyright: ignore[reportUnknownArgumentType]
        else:
            base[key] = value
    return base


def _load_toml(source: Source, name: str) -> dict[str, Any]:
    path = source.path / name
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise DefaultsError(
            f"{path} is not valid TOML ({e}). Fix the syntax, or restore it with "
            f'"git -C {source.path} checkout {name}", then retry.'
        ) from None


def load_defaults(source: Source) -> dict[str, Any]:
    merged = _load_toml(source, _DEFAULTS)
    if (source.path / _OVERRIDES).is_file():
        _merge(merged, _load_toml(source, _OVERRIDES))
    for principle in merged.get("principles", []):
        for condition in principle.get("applies", []):
            if condition not in CONDITIONS:
                raise DefaultsError(
                    f'Principle "{principle.get("id")}" has unknown condition '
                    f'"{condition}". Use one of: {", ".join(sorted(CONDITIONS))}.'
                )
    return merged


def _parse_value(value: str) -> object:
    try:
        return tomllib.loads(f"v = {value}")["v"]
    except tomllib.TOMLDecodeError:
        return value


def _is_table_array(value: object) -> bool:
    return isinstance(value, list) and any(
        isinstance(v, dict) for v in cast("list[Any]", value)
    )


def _settings(data: Mapping[str, Any], prefix: str = "") -> list[str]:
    """Dotted keys of the single settings `defaults set` may change."""
    keys: list[str] = []
    for name, value in data.items():
        key = f"{prefix}{name}"
        if isinstance(value, dict):
            keys += _settings(cast("dict[str, Any]", value), key + ".")
        elif not _is_table_array(value) and key != "schema":
            keys.append(key)
    return keys


def _kind(value: object) -> str:
    if isinstance(value, bool):
        return "true or false"
    if isinstance(value, int):
        return "a whole number"
    if isinstance(value, float):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        items = cast("list[Any]", value)
        return "a list of text" if items and isinstance(items[0], str) else "a list"
    return type(value).__name__


def _same_kind(current: object, new: object) -> bool:
    if type(current) is not type(new):
        return False
    if isinstance(current, list) and current:
        first: object = cast("list[object]", current)[0]
        return all(type(v) is type(first) for v in cast("list[object]", new))
    return True


def _check_setting(merged: dict[str, Any], key: str, value: object) -> None:
    """Refuse keys that aren't single kit settings, and values of another type."""
    settable = f"Settings you can set: {', '.join(_settings(merged))}."
    unknown = DefaultsError(f'"{key}" is not a kit default. {settable}')
    *parents, leaf = key.split(".")
    table = merged
    for part in parents:
        child: object = table.get(part)
        if not isinstance(child, dict):
            raise unknown
        table = cast("dict[str, Any]", child)
    if leaf not in table:
        raise unknown
    current: object = table[leaf]
    if isinstance(current, dict) or _is_table_array(current):
        raise DefaultsError(
            f'"{key}" is a table of settings, not one setting. {settable}'
        )
    if not _same_kind(current, value):
        example = toml_write.dumps({"v": current}).removeprefix("v = ").strip()
        raise DefaultsError(
            f"{key} must be {_kind(current)}, like its current value {example}. "
            f"Pass e.g. --value '{example}'."
        )


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    if done.returncode != 0:
        raise DefaultsError(
            f"git {args[0]} failed in {repo}: {done.stderr.strip()}. "
            "Fix the repository state there, then retry."
        )
    return done.stdout.strip()


def set_default(
    source: Source,
    key: str,
    value: str,
    project: str,
    reason: str,
    trailers: list[str],
    today: date,
) -> str:
    if not source.live:
        raise SourceNotLive(
            "Cannot change kit defaults: no alpha source checkout is available "
            f"({source.reason}). Record the wish in the project's decision log "
            "instead, or set ALPHA_SOURCE and retry."
        )
    parsed = _parse_value(value)
    _check_setting(load_defaults(source), key, parsed)
    overrides_path = source.path / _OVERRIDES
    changelog = source.path / _CHANGELOG
    before = {
        f: f.read_text() if f.is_file() else None for f in (overrides_path, changelog)
    }
    data: dict[str, Any] = tomllib.loads(before[overrides_path] or "")
    *parents, leaf = key.split(".")
    table: dict[str, Any] = data
    for part in parents:
        child: Any = table.get(part)
        if not isinstance(child, dict):
            child = {}
            table[part] = child
        table = cast("dict[str, Any]", child)
    table[leaf] = parsed
    message = f"chore(defaults): Set {leaf}"
    if trailers:
        message += "\n\n" + "\n".join(trailers)
    try:
        overrides_path.write_text(_OVERRIDES_HEADER + toml_write.dumps(data))
        with changelog.open("a") as f:
            f.write(f"- {today} · {key} = {value} · from {project} · {reason}\n")
        _git(source.path, "add", _OVERRIDES, _CHANGELOG)
        _git(source.path, "commit", "-q", "-m", message, "--", _OVERRIDES, _CHANGELOG)
    except (DefaultsError, OSError):
        _restore(source.path, before)
        raise
    return _git(source.path, "rev-parse", "--short", "HEAD")


def _restore(repo: Path, before: dict[Path, str | None]) -> None:
    """Put the defaults files back as they were and unstage them (best effort)."""
    for path, text in before.items():
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(text)
    subprocess.run(
        ["git", "-C", str(repo), "reset", "-q", "--", _OVERRIDES, _CHANGELOG],
        capture_output=True,
    )
