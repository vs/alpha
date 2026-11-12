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
USER_OVERRIDES = "overrides.toml"
USER_CHANGELOG = "CHANGELOG.md"
USER_RECIPES = "recipes"
_OVERRIDES_HEADER = '# Managed by "alpha defaults set". Do not edit by hand.\n'
_CHANGELOG_HEADER = (
    '# Your alpha defaults\n\nEntries are appended by "alpha defaults set".\n'
)


class DefaultsError(Exception):
    pass


@dataclass(frozen=True)
class Source:
    path: Path
    checkout: bool
    user: Path | None = None


def user_dir(env: Mapping[str, str], home: Path) -> Path:
    given = env.get("ALPHA_CONFIG_DIR")
    return Path(given) if given else home / ".config/alpha"


def locate_source(plugin_root: Path, env: Mapping[str, str], home: Path) -> Source:
    user = user_dir(env, home)
    given = env.get("ALPHA_SOURCE")
    if not given:
        return Source(plugin_root, False, user)
    checkout = Path(given)
    if not (checkout / _DEFAULTS).is_file():
        raise DefaultsError(
            f"ALPHA_SOURCE is {checkout}, which has no {_DEFAULTS}, so it isn't an "
            "alpha checkout. Point it at one, or unset it to use the installed "
            "plugin."
        )
    return Source(checkout, True, user)


def _merge(base: dict[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in over.items():
        current = base.get(key)
        if isinstance(value, Mapping) and isinstance(current, dict):
            _merge(current, value)  # pyright: ignore[reportUnknownArgumentType]
        else:
            base[key] = value
    return base


def _load_toml(path: Path, restore: str) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise DefaultsError(
            f"{path} is not valid TOML ({e}). Fix the syntax, or {restore}, then retry."
        ) from None


SURVEY = "defaults/survey.toml"


def load_survey(source: Source) -> dict[str, list[str]]:
    """The globs `alpha adopt survey` looks for, by kind (spec §5b): from the
    checkout when it has them, otherwise the plugin's."""
    path = source.path / SURVEY
    if not path.is_file():
        path = Path(__file__).resolve().parents[2] / SURVEY
    data = _load_toml(path, "reinstall the alpha plugin")
    out: dict[str, list[str]] = {}
    for key, value in data.items():
        if not isinstance(value, list) or not all(
            isinstance(g, str) for g in cast(list[object], value)
        ):
            raise DefaultsError(
                f"{path}: {key} must be a list of globs. Fix it, or reinstall the "
                "alpha plugin."
            )
        out[key] = cast(list[str], value)
    return out


def load_defaults(source: Source) -> dict[str, Any]:
    restore = (
        f'restore it with "git -C {source.path} checkout {_DEFAULTS}"'
        if source.checkout
        else "reinstall the alpha plugin"
    )
    merged = _load_toml(source.path / _DEFAULTS, restore)
    mine = None if source.user is None else source.user / USER_OVERRIDES
    if mine is not None and mine.is_file():
        _merge(merged, _load_toml(mine, "delete it to go back to the kit's defaults"))
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


def set_default(
    source: Source,
    key: str,
    value: str,
    project: str,
    reason: str,
    today: date,
) -> Path:
    if source.user is None:
        raise DefaultsError(
            "Cannot save a default: there is no folder for your alpha defaults. "
            "Set ALPHA_CONFIG_DIR to one, then retry."
        )
    parsed = _parse_value(value)
    _check_setting(load_defaults(source), key, parsed)
    overrides_path = source.user / USER_OVERRIDES
    changelog = source.user / USER_CHANGELOG
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
    log = before[changelog] or _CHANGELOG_HEADER
    try:
        source.user.mkdir(parents=True, exist_ok=True)
        overrides_path.write_text(_OVERRIDES_HEADER + toml_write.dumps(data))
        changelog.write_text(
            log + list_gap(log) + f"- {today} · {key} = {value} · from {project} · "
            f"{reason}\n"
        )
    except OSError as e:
        _restore(before)
        raise DefaultsError(
            f"Could not write {e.filename or source.user}: {e.strerror or e}. Check "
            "its permissions and free space, then retry."
        ) from None
    return overrides_path


def list_gap(existing: str) -> str:
    """What to write before a new list item: a blank line unless the file is
    empty or already ends in a list item (Markdown wants a list set apart from
    the paragraph above it), plus a newline if the last line lacks one."""
    if not existing:
        return ""
    end = "" if existing.endswith("\n") else "\n"
    text = [line for line in existing.splitlines() if line.strip()]
    if not text:  # only whitespace: no paragraph to set the list apart from
        return end
    return end if text[-1].startswith("- ") else end + "\n"


def _restore(before: dict[Path, str | None]) -> None:
    for path, text in before.items():
        try:
            if text is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(text)
        except OSError:
            continue
