"""Stack recipes: commands, globs and skeleton templates per stack."""

import fnmatch
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from alpha.validate import AnswersError, unmatchable

if TYPE_CHECKING:
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
    templates: dict[str, str]  # output relpath -> template text
    ignores: list[str]  # .gitignore entries, relative to the component
    dependabot: str  # Dependabot package-ecosystem; "" for none
    why: dict[str, str]  # bootstrap tool -> reason, for the dependency log
    ci: CiSetup
    proven: bool  # False for a recipe drafted in a project interview


class RecipeError(AnswersError):
    """A recipe that can't be used; the message names the field and the fix."""


COMMAND_KEYS = (*CHECK_STEPS, "format", "format_file", "lint_file")
_ACTION = re.compile(r"[\w.-]+/[\w.-]+(/[\w./-]+)?@(v\d+(\.\d+){0,2}|[0-9a-f]{40})")
_TEMPLATE_VALUE = re.compile(r"(?<!\$)\$(?:\{(name|slug)\}|(name|slug)\b)")


def matches(path: str, globs: list[str]) -> bool:
    """Whether path matches any glob, "**" spanning any depth."""

    def parts(p: list[str], g: list[str]) -> bool:
        if not g:
            return not p
        if g[0] == "**":
            return any(parts(p[k:], g[1:]) for k in range(len(p) + 1))
        return bool(p) and fnmatch.fnmatchcase(p[0], g[0]) and parts(p[1:], g[1:])

    return any(parts(path.split("/"), glob.split("/")) for glob in globs)


def _fail(where: str, problem: str, fix: str) -> RecipeError:
    return RecipeError(f"{where}: {problem}. {fix}")


def _texts(value: object, where: str, *, globs: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise _fail(where, "must be a list", "Write it as a JSON list of strings")
    out: list[str] = []
    for i, item in enumerate(cast("list[object]", value)):
        here = f"{where}[{i}]"
        if not isinstance(item, str) or not item.strip():
            raise _fail(here, "must be non-empty text", "Remove it or fill it in")
        if globs and unmatchable(item):
            raise _fail(
                here,
                f"{item!r} must be relative to the component folder",
                'Write e.g. "src/**" or "Cargo.lock": no leading "/" or "./", no '
                'trailing "/", no ".." or "//"',
            )
        if not globs and item.startswith("/"):
            raise _fail(here, f"{item!r} starts with /", "Make it relative")
        out.append(item)
    return out


def _mapping(value: object, where: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _fail(where, "must be an object of text values", 'Write e.g. {"a": "b"}')
    data = cast("dict[object, object]", value)
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise _fail(where, "must map text to text", 'Write e.g. {"a": "b"}')
    return cast("dict[str, str]", data)


def recipe_from_data(
    stack: str, data: Mapping[str, Any], where: str, template_dir: Path | None
) -> Recipe:
    """Validate a recipe from a kit TOML file or a drafted JSON object.

    Kit recipes name template files in `files` (read from template_dir/stack);
    drafted recipes give `templates` inline.
    """

    def get(key: str) -> object:
        if key not in data:
            raise _fail(f"{where}.{key}", "is missing", f'Add "{key}"')
        return data[key]

    bootstrap = _texts(get("bootstrap"), f"{where}.bootstrap")
    raw = get("commands")
    if not isinstance(raw, dict):
        raise _fail(
            f"{where}.commands", "must be an object", "List each step's command"
        )
    commands_in = cast("dict[str, object]", raw)
    commands: dict[str, str] = {}
    for key in COMMAND_KEYS:
        here = f"{where}.commands.{key}"
        if key not in commands_in:
            raise _fail(here, "is missing", 'Add it; use "" when the stack has none')
        value = commands_in[key]
        if not isinstance(value, str):
            raise _fail(here, "must be text", "Write the shell command")
        if key in ("setup", "test") and not value.strip():
            raise _fail(
                here, "is empty", "Every stack needs a setup and a test command"
            )
        if key in ("format_file", "lint_file") and value and "{file}" not in value:
            raise _fail(here, "doesn't say where the file goes", "Put {file} in it")
        commands[key] = value
    lists = {
        key: _texts(get(key), f"{where}.{key}", globs=key != "allow")
        for key in (
            "lockfiles",
            "manifests",
            "source_globs",
            "test_globs",
            "exclude_globs",
            "allow",
        )
    }
    ignores = _texts(get("ignores"), f"{where}.ignores")
    why = _mapping(get("why"), f"{where}.why")
    ci_raw = get("ci")
    if not isinstance(ci_raw, dict):
        raise _fail(
            f"{where}.ci", "must be an object", 'Write {"steps": [], "env": {}}'
        )
    ci_data = cast("dict[str, object]", ci_raw)
    steps_raw = ci_data.get("steps", [])
    if not isinstance(steps_raw, list):
        raise _fail(f"{where}.ci.steps", "must be a list", "List GitHub Actions steps")
    steps: list[dict[str, Any]] = []
    for i, step in enumerate(cast("list[object]", steps_raw)):
        here = f"{where}.ci.steps[{i}]"
        if not isinstance(step, dict):
            raise _fail(here, "must be an object", 'Write {"uses": "owner/repo@v1"}')
        step_data = cast("dict[str, Any]", step)
        uses = step_data.get("uses")
        if not isinstance(uses, str) or not _ACTION.fullmatch(uses):
            raise _fail(
                here,
                f"uses {uses!r} isn't a pinned action",
                "Pin it to a release tag (owner/repo@v4 or @v4.2.1) or a full "
                "commit SHA",
            )
        steps.append(step_data)
    env = _mapping(ci_data.get("env", {}), f"{where}.ci.env")
    dependabot = get("dependabot")
    if not isinstance(dependabot, str):
        raise _fail(f"{where}.dependabot", "must be text", 'Name the ecosystem, or ""')
    proven = data.get("proven", False)
    if not isinstance(proven, bool):
        raise _fail(f"{where}.proven", "must be true or false", "Use true or false")
    if template_dir is not None and "files" in data:
        names = _mapping(data["files"], f"{where}.files")
        templates = {
            rel: (template_dir / stack / name).read_text()
            for rel, name in names.items()
        }
    else:
        templates = _mapping(get("templates"), f"{where}.templates")
    if not templates:
        raise _fail(
            f"{where}.templates", "is empty", "Give the manifest and a setup test"
        )
    for rel in templates:
        if unmatchable(rel):
            raise _fail(
                f"{where}.templates",
                f"{rel!r} isn't a path inside the component",
                'Use relative paths like "tests/setup.sh"',
            )
    if not any(matches(rel, lists["test_globs"]) for rel in templates):
        raise _fail(
            f"{where}.templates",
            "has no setup test (no template matches test_globs)",
            "Add a test that checks the toolchain itself, e.g. tests/setup.<ext>",
        )
    return Recipe(
        stack=stack,
        bootstrap=bootstrap,
        commands=commands,
        lockfiles=lists["lockfiles"],
        manifests=lists["manifests"],
        source_globs=lists["source_globs"],
        test_globs=lists["test_globs"],
        exclude_globs=lists["exclude_globs"],
        allow=lists["allow"],
        templates=templates,
        ignores=ignores,
        dependabot=dependabot,
        why=why,
        ci=CiSetup(steps=steps, env=env),
        proven=proven,
    )


def load_recipe(stack: str) -> Recipe:
    path = RECIPES_DIR / f"{stack}.toml"
    if not path.is_file():
        known = sorted(p.stem for p in RECIPES_DIR.glob("*.toml"))
        raise RecipeError(
            f'No recipe for stack "{stack}". Use one of: {", ".join(known)}.'
        )
    data = tomllib.loads(path.read_text())
    return recipe_from_data(stack, data, f"recipes/{stack}.toml", RECIPES_DIR)


def render_template(text: str, name: str, slug: str) -> str:
    """Fill in $name and $slug (or ${name}, ${slug}); every other $ stays."""
    values = {"name": name, "slug": slug}
    return _TEMPLATE_VALUE.sub(lambda m: values[m.group(1) or m.group(2)], text)


def check_commands(commands: Mapping[str, str]) -> list[tuple[str, str]]:
    """(step, command) for each check step the component has, in CI order."""
    return [(step, commands[step]) for step in CHECK_STEPS if commands.get(step)]


def render_component(
    component: Component, project_slug: str, recipe: Recipe | None = None
) -> dict[str, str]:
    """Render a component's skeleton files, keyed by path from the project root."""
    recipe = recipe or load_recipe(component.stack)
    base = Path(component.path)
    return {
        (base / relpath).as_posix(): render_template(text, component.name, project_slug)
        for relpath, text in recipe.templates.items()
    }
