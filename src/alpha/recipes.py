"""Stack recipes: commands, globs and skeleton templates per stack."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from string import Template

from alpha.answers import Component

RECIPES_DIR = Path(__file__).resolve().parents[2] / "recipes"


@dataclass(frozen=True)
class Recipe:
    stack: str
    bootstrap: list[str]
    commands: dict[str, str]
    lockfiles: list[str]
    manifests: list[str]
    source_globs: list[str]
    test_globs: list[str]
    allow: list[str]
    files: dict[str, str]  # output relpath -> template name


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
        allow=data["allow"],
        files=data["files"],
    )


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
