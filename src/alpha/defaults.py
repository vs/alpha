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


def load_defaults(source: Source) -> dict[str, Any]:
    merged = tomllib.loads((source.path / _DEFAULTS).read_text())
    overrides = source.path / _OVERRIDES
    if overrides.is_file():
        _merge(merged, tomllib.loads(overrides.read_text()))
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
        raise DefaultsError(
            "Cannot change kit defaults: no alpha source checkout is available "
            f"({source.reason}). Record the wish in the project's decision log "
            "instead, or set ALPHA_SOURCE and retry."
        )
    overrides_path = source.path / _OVERRIDES
    data: dict[str, Any] = (
        tomllib.loads(overrides_path.read_text()) if overrides_path.is_file() else {}
    )
    *parents, leaf = key.split(".")
    table: dict[str, Any] = data
    for part in parents:
        child: Any = table.get(part)
        if not isinstance(child, dict):
            child = {}
            table[part] = child
        table = cast("dict[str, Any]", child)
    table[leaf] = _parse_value(value)
    overrides_path.write_text(_OVERRIDES_HEADER + toml_write.dumps(data))

    changelog = source.path / _CHANGELOG
    with changelog.open("a") as f:
        f.write(f"- {today} · {key} = {value} · from {project} · {reason}\n")

    _git(source.path, "add", _OVERRIDES, _CHANGELOG)
    message = f"chore(defaults): Set {leaf}"
    if trailers:
        message += "\n\n" + "\n".join(trailers)
    _git(source.path, "commit", "-q", "-m", message)
    return _git(source.path, "rev-parse", "--short", "HEAD")
