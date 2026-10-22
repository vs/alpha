"""Stack recipes: commands, globs and skeleton templates per stack."""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

from alpha.answers import Component

RECIPES_DIR = Path(__file__).resolve().parents[2] / "recipes"
# What CI runs per component, in order; bootstrap runs the same commands.
CHECK_STEPS = ("setup", "format_check", "lint", "typecheck", "test")


@dataclass(frozen=True)
class CiSetup:
    """GitHub Actions steps that install the stack's toolchain, and job env.

    Strings in steps may hold ${dir}: the component folder plus "/", or
    nothing for a component at the project root.
    """

    steps: list[dict[str, Any]]
    env: dict[str, str]


@dataclass(frozen=True)
class Recipe:
    stack: str
    bootstrap: list[str]
    commands: dict[str, str]
    lockfiles: list[str]
    manifests: list[str]
    source_globs: list[str]
    test_globs: list[str]
    exclude_globs: list[str]
    allow: list[str]
    files: dict[str, str]  # output relpath -> template name
    ignores: list[str]  # .gitignore entries, relative to the component
    dependabot: str  # Dependabot package-ecosystem
    why: dict[str, str]  # bootstrap tool -> reason, for the dependency log
    ci: CiSetup


def load_recipe(stack: str) -> Recipe:
    path = RECIPES_DIR / f"{stack}.toml"
    if not path.is_file():
        known = sorted(p.stem for p in RECIPES_DIR.glob("*.toml"))
        raise ValueError(
            f'No recipe for stack "{stack}". Use one of: {", ".join(known)}.'
        )
    data = tomllib.loads(path.read_text())
    return Recipe(
        stack=data["stack"],
        bootstrap=data["bootstrap"],
        commands=data["commands"],
        lockfiles=data["lockfiles"],
        manifests=data["manifests"],
        source_globs=data["source_globs"],
        test_globs=data["test_globs"],
        exclude_globs=data["exclude_globs"],
        allow=data["allow"],
        files=data["files"],
        ignores=data["ignores"],
        dependabot=data["dependabot"],
        why=data["why"],
        ci=CiSetup(steps=data["ci"]["steps"], env=data["ci"]["env"]),
    )


def check_commands(commands: Mapping[str, str]) -> list[tuple[str, str]]:
    """(step, command) for each check step the component has, in CI order."""
    return [(step, commands[step]) for step in CHECK_STEPS if commands.get(step)]


def render_component(component: Component, project_slug: str) -> dict[str, str]:
    """Render a component's skeleton files, keyed by path from the project root."""
    recipe = load_recipe(component.stack)
    values = {"name": component.name, "slug": project_slug}
    base = Path(component.path)
    rendered: dict[str, str] = {}
    for relpath, template in recipe.files.items():
        text = (RECIPES_DIR / component.stack / template).read_text()
        rendered[(base / relpath).as_posix()] = Template(text).substitute(values)
    return rendered
