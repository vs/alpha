from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from alpha.baseline import BASELINE_STEPS, NOT_BASELINED, Baseline, baseline_from_data
from alpha.defaults import USER_RECIPES, DefaultsError, locate_source
from alpha.validate import AnswersError, unmatchable

if TYPE_CHECKING:
    from alpha.answers import Component

RECIPES_DIR = Path(__file__).resolve().parents[2] / "recipes"
CHECK_STEPS = ("setup", "format_check", "lint", "typecheck", "structure", "test")
OPTIONAL_STEPS = frozenset({"structure"})


@dataclass(frozen=True)
class CiSetup:
    steps: list[dict[str, Any]]
    env: dict[str, str]


@dataclass(frozen=True)
class StackRule:
    id: str
    rule: str


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
    templates: dict[str, str]
    ignores: list[str]
    dependabot: str
    why: dict[str, str]
    ci: CiSetup
    proven: bool
    rules: list[StackRule]
    # Optional: the command that writes a coverage report, and the report path
    # (relative to the component). A stack with both gets a diff coverage check.
    coverage: str = ""
    coverage_report: str = ""
    # How each step's findings read, for a baseline (spec §8b); keyed by step.
    baselines: Mapping[str, Baseline] = field(default_factory=lambda: {})
    # File names whose folder the adoption survey lists as a candidate.
    detect: tuple[str, ...] = ()
    # Runs an existing repo's own tools (spec §5b, A1): no templates or
    # bootstrap of its own, proven on the repo's code.
    adopted: bool = False


class RecipeError(AnswersError):
    pass


COMMAND_KEYS = (*CHECK_STEPS, "format", "format_file", "lint_file")
_RECIPE_KEYS = frozenset(
    {
        "stack",
        "proven",
        "proven_hash",
        "bootstrap",
        "commands",
        "lockfiles",
        "manifests",
        "source_globs",
        "test_globs",
        "exclude_globs",
        "ignores",
        "allow",
        "why",
        "ci",
        "dependabot",
        "templates",
        "files",
        "rules",
        "coverage",
        "coverage_report",
        "baseline",
        "detect",
        "adopted",
        "extends",
    }
)
_STEP_KEYS = frozenset({"uses", "version", "with", "name", "id", "env"})
# Dependabot's package-ecosystem values (its config schema, 2026-10).
DEPENDABOT_ECOSYSTEMS = frozenset(
    {
        "bazel",
        "bun",
        "bundler",
        "cargo",
        "composer",
        "conda",
        "deno",
        "devcontainers",
        "docker",
        "docker-compose",
        "dotnet-sdk",
        "elm",
        "github-actions",
        "gitsubmodule",
        "gomod",
        "gradle",
        "helm",
        "julia",
        "maven",
        "mix",
        "nix",
        "npm",
        "nuget",
        "opentofu",
        "pip",
        "pre-commit",
        "pub",
        "rust-toolchain",
        "sbt",
        "swift",
        "terraform",
        "uv",
        "vcpkg",
    }
)
_RESERVED = (".git", ".claude", ".github")
_ALLOW = re.compile(r"Bash\(([A-Za-z0-9_.-]+)((?: [A-Za-z0-9_.=/-]+)*):\*\)")
_ACTION = re.compile(r"[\w.-]+/[\w.-]+(/[\w./-]+)?@(v\d+(\.\d+){0,2}|[0-9a-f]{40})")
_SHA_ACTION = re.compile(r"[\w.-]+/[\w.-]+(/[\w./-]+)?@[0-9a-f]{40}")
_RULE_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_TEMPLATE_VALUE = re.compile(r"(?<!\$)\$(?:\{(name|slug)\}|(name|slug)\b)")


def matches(path: str, globs: list[str]) -> bool:

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
        _one_line(item, here)
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


def _one_line(text: str, where: str) -> None:
    """Commands, globs and reasons land in one line of .gitignore, a shell
    or a Markdown table, where a line break would split them."""
    if "\n" in text or "\r" in text:
        raise _fail(where, f"{text!r} has a line break", "Write it on one line")


def _plain(value: object) -> bool:
    if isinstance(value, bool | int | str):
        return not isinstance(value, float)
    if isinstance(value, list):
        return all(_plain(v) for v in cast("list[object]", value))
    if isinstance(value, dict):
        items = cast("dict[object, object]", value).items()
        return all(isinstance(k, str) and _plain(v) for k, v in items)
    return False


def _unknown(
    keys: object, allowed: frozenset[str] | tuple[str, ...], where: str
) -> None:
    extra = sorted(
        str(k) for k in cast("dict[object, object]", keys) if k not in allowed
    )
    if extra:
        raise _fail(
            where,
            f"unknown {'key' if len(extra) == 1 else 'keys'} {', '.join(extra)}",
            f"Use only: {', '.join(sorted(allowed))}",
        )


def _first_word(command: str) -> str:
    words = [w for w in command.split() if "=" not in w]
    return words[0] if words else ""


def _mapping(value: object, where: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _fail(where, "must be an object of text values", 'Write e.g. {"a": "b"}')
    data = cast("dict[object, object]", value)
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise _fail(where, "must map text to text", 'Write e.g. {"a": "b"}')
    return cast("dict[str, str]", data)


def _rules(value: object, where: str) -> list[StackRule]:
    if not isinstance(value, list):
        raise _fail(
            where, "must be a list", 'Write e.g. [{"id": "no-x", "rule": "Don\'t x."}]'
        )
    rules: list[StackRule] = []
    for i, item in enumerate(cast("list[object]", value)):
        here = f"{where}[{i}]"
        if not isinstance(item, dict):
            raise _fail(here, "must be an object", 'Write {"id": "…", "rule": "…"}')
        data = cast("dict[str, object]", item)
        _unknown(data, ("id", "rule"), here)
        rule_id, text = data.get("id"), data.get("rule")
        if not isinstance(rule_id, str) or not _RULE_ID.fullmatch(rule_id):
            raise _fail(
                f"{here}.id",
                f"{rule_id!r} isn't a lowercase id with hyphens",
                'Write e.g. "typed-boundaries"',
            )
        if any(r.id == rule_id for r in rules):
            raise _fail(f"{here}.id", f"{rule_id!r} is used twice", "Rename one")
        if not isinstance(text, str) or not text.strip():
            raise _fail(f"{here}.rule", "must be non-empty text", "Write the rule")
        _one_line(text, f"{here}.rule")
        rules.append(StackRule(id=rule_id, rule=text))
    return rules


def _baselines(
    value: object, where: str, commands: Mapping[str, str]
) -> dict[str, Baseline]:
    if not isinstance(value, dict):
        raise _fail(where, "must be an object", "Key each entry by its step, e.g. lint")
    out: dict[str, Baseline] = {}
    for step, entry in cast("dict[str, object]", value).items():
        here = f"{where}.{step}"
        if step in NOT_BASELINED:
            raise _fail(here, f"can't be baselined: {NOT_BASELINED[step]}", "Remove it")
        if step not in BASELINE_STEPS:
            raise _fail(
                here,
                "isn't a step a baseline can hold",
                f"Use one of: {', '.join(BASELINE_STEPS)}",
            )
        if not commands.get(step):
            raise _fail(
                here,
                f"is set, but commands.{step} is empty",
                f"Give commands.{step}, or remove this entry",
            )
        file_slot = step == "lint" and bool(commands.get("lint_file"))
        out[step] = baseline_from_data(entry, here, _fail, file_slot=file_slot)
    return out


_GLOB_CHARS = frozenset("*?[]{}")


def _detect(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, dict):
        raise _fail(where, "must be an object", 'Write {"markers": ["Cargo.toml"]}')
    data = cast("dict[str, object]", value)
    _unknown(data, ("markers",), where)
    markers = _texts(data.get("markers", []), f"{where}.markers")
    for i, name in enumerate(markers):
        if "/" in name or set(name) & _GLOB_CHARS:
            raise _fail(
                f"{where}.markers[{i}]",
                f"{name!r} isn't a plain file name",
                'Name the file itself, e.g. "Cargo.toml": its folder is the component',
            )
    return tuple(markers)


def recipe_from_data(
    stack: str,
    data: Mapping[str, Any],
    where: str,
    template_dir: Path | None,
    *,
    generated: bool = False,
    checkout: Path | None = None,
) -> Recipe:

    _unknown(data, _RECIPE_KEYS, where)

    def get(key: str) -> object:
        if key not in data:
            raise _fail(f"{where}.{key}", "is missing", f'Add "{key}"')
        return data[key]

    adopted = data.get("adopted", False)
    if not isinstance(adopted, bool):
        raise _fail(f"{where}.adopted", "must be true or false", "Use true or false")
    if "extends" in data and not adopted:
        raise _fail(
            f"{where}.extends",
            "is set on a recipe that isn't adopted",
            'Only an adopted recipe extends a kit one: add "adopted": true, or '
            "remove extends",
        )
    bootstrap = _texts(get("bootstrap"), f"{where}.bootstrap")
    if adopted and bootstrap:
        raise _fail(
            f"{where}.bootstrap",
            "must be empty in an adopted recipe: adopting a repo doesn't install "
            "tools into it",
            "Remove the commands; adding a missing tool is a step of the adoption plan",
        )
    raw = get("commands")
    if not isinstance(raw, dict):
        raise _fail(
            f"{where}.commands", "must be an object", "List each step's command"
        )
    commands_in = cast("dict[str, object]", raw)
    _unknown(commands_in, COMMAND_KEYS, f"{where}.commands")
    commands: dict[str, str] = {}
    for key in COMMAND_KEYS:
        here = f"{where}.commands.{key}"
        if key not in commands_in and key in OPTIONAL_STEPS:
            commands[key] = ""
            continue
        if key not in commands_in:
            raise _fail(here, "is missing", 'Add it; use "" when the stack has none')
        value = commands_in[key]
        if not isinstance(value, str):
            raise _fail(here, "must be text", "Write the shell command")
        _one_line(value, here)
        if key in ("setup", "test") and not value.strip():
            if key == "test" and adopted:
                commands[key] = value  # a repo without tests: a plan step adds them
                continue
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
    for tool, reason in why.items():
        _one_line(tool, f"{where}.why")
        _one_line(reason, f"{where}.why.{tool}")
    ci_raw = get("ci")
    if not isinstance(ci_raw, dict):
        raise _fail(
            f"{where}.ci", "must be an object", 'Write {"steps": [], "env": {}}'
        )
    ci_data = cast("dict[str, object]", ci_raw)
    _unknown(ci_data, ("steps", "env"), f"{where}.ci")
    steps_raw = ci_data.get("steps", [])
    if not isinstance(steps_raw, list):
        raise _fail(f"{where}.ci.steps", "must be a list", "List GitHub Actions steps")
    steps: list[dict[str, Any]] = []
    for i, step in enumerate(cast("list[object]", steps_raw)):
        here = f"{where}.ci.steps[{i}]"
        if not isinstance(step, dict):
            raise _fail(here, "must be an object", 'Write {"uses": "owner/repo@v1"}')
        step_data = cast("dict[str, Any]", step)
        _unknown(step_data, _STEP_KEYS, here)
        if not _plain(step_data):
            raise _fail(
                here,
                "has a value that isn't text, a whole number or true/false",
                "Write every value as text (quote numbers like versions)",
            )
        uses = step_data.get("uses")
        if generated:
            pinned = isinstance(uses, str) and _ACTION.fullmatch(uses)
        else:
            pinned = isinstance(uses, str) and _SHA_ACTION.fullmatch(uses)
        if not pinned and checkout is not None:
            raise _fail(
                here,
                f"uses {uses!r}, which isn't pinned to a full commit SHA",
                f"The alpha checkout at {checkout} is older than the plugin, and "
                f"its {stack} recipe replaces the plugin's. Update it (git -C "
                f"{checkout} pull) or unset ALPHA_SOURCE, then retry",
            )
        if not pinned:
            raise _fail(
                here,
                f"uses {uses!r}, which isn't pinned to a full commit SHA",
                "Pin it to the commit SHA of the latest release tag "
                "(`git ls-remote https://github.com/<owner>/<repo> "
                "refs/tags/<tag>`, the peeled `^{}` line for an annotated tag) "
                "as owner/repo@<40 hex digits>, and put the tag in `version`",
            )
        version = step_data.get("version")
        if version is None and not generated:
            raise _fail(
                here,
                "has no `version`",
                'Add the release tag the SHA belongs to, e.g. "version": "v4.2.1"',
            )
        if version is not None:
            if not isinstance(version, str):
                raise _fail(here, "`version` must be text", "Write the release tag")
            _one_line(version, f"{here}.version")
        steps.append(step_data)
    env = _mapping(ci_data.get("env", {}), f"{where}.ci.env")
    dependabot = get("dependabot")
    if not isinstance(dependabot, str):
        raise _fail(f"{where}.dependabot", "must be text", 'Name the ecosystem, or ""')
    if dependabot and dependabot not in DEPENDABOT_ECOSYSTEMS:
        raise _fail(
            f"{where}.dependabot",
            f"{dependabot!r} isn't a Dependabot ecosystem",
            f'Use one of: {", ".join(sorted(DEPENDABOT_ECOSYSTEMS))}, or ""',
        )
    coverage = data.get("coverage", "")
    coverage_report = data.get("coverage_report", "")
    for key, value in (("coverage", coverage), ("coverage_report", coverage_report)):
        if not isinstance(value, str):
            raise _fail(f"{where}.{key}", "must be text", 'Write it, or "" for none')
        _one_line(value, f"{where}.{key}")
    if bool(coverage) != bool(coverage_report):
        missing = "coverage_report" if coverage else "coverage"
        raise _fail(
            f"{where}.{missing}",
            "is empty but its pair is set",
            "Give both the coverage command and the report path it writes, or neither",
        )
    if coverage_report and unmatchable(coverage_report):
        raise _fail(
            f"{where}.coverage_report",
            f"{coverage_report!r} must be relative to the component folder",
            'Write e.g. "coverage.xml"',
        )
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
        templates = _mapping(
            data.get("templates", {}) if adopted else get("templates"),
            f"{where}.templates",
        )
    if not templates and not adopted:
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
        if rel.split("/")[0] in _RESERVED:
            raise _fail(
                f"{where}.templates",
                f"{rel!r} is inside {rel.split('/')[0]}/, which belongs to git, "
                "alpha or its CI",
                "Leave it out; alpha writes those files itself",
            )
    if not adopted and not any(matches(rel, lists["test_globs"]) for rel in templates):
        raise _fail(
            f"{where}.templates",
            "has no setup test (no template matches test_globs)",
            "Add a test that checks the toolchain itself, e.g. tests/setup.<ext>",
        )
    tools = {_first_word(c) for c in [*bootstrap, *commands.values()] if c}
    for i, rule in enumerate(lists["allow"]):
        found = _ALLOW.fullmatch(rule)
        if found is None or found.group(1) not in tools:
            raise _fail(
                f"{where}.allow[{i}]",
                f"{rule!r} isn't a narrow rule for one of the recipe's own tools",
                f"Write Bash(<tool> <args>:*) for a tool its commands use "
                f"({', '.join(sorted(tools))}), e.g. Bash({sorted(tools)[0]} test:*)"
                if tools
                else "Remove it",
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
        rules=_rules(data.get("rules", []), f"{where}.rules"),
        coverage=coverage,
        coverage_report=coverage_report,
        baselines=_baselines(data.get("baseline", {}), f"{where}.baseline", commands),
        detect=_detect(data.get("detect", {}), f"{where}.detect"),
        adopted=adopted,
    )


# What an adopted recipe takes from the kit recipe it extends: not what
# installs or writes into the repo (bootstrap and its reasons, templates) nor
# coverage, which needs a plugin the repo may not have.
_INHERITED = (
    "lockfiles",
    "manifests",
    "source_globs",
    "test_globs",
    "exclude_globs",
    "ignores",
    "allow",
    "ci",
    "dependabot",
    "rules",
)


def adopted_data(entry: Mapping[str, Any], kit: Mapping[str, Any]) -> dict[str, Any]:
    """An adopted recipe's entry over the kit recipe it extends (spec §5b, A1).
    A step whose command the entry changes drops the kit's baseline reader for
    it, which reads the kit's tool; so does `lint_file` for the reader's
    `file_command`."""
    merged: dict[str, Any] = {k: kit[k] for k in _INHERITED if k in kit}
    merged.update({"bootstrap": [], "why": {}, "templates": {}})
    kit_commands = cast("dict[str, str]", kit.get("commands", {}))
    commands = {**kit_commands, **cast("dict[str, str]", entry.get("commands", {}))}
    readers: dict[str, Any] = {}
    for step, reader in cast("dict[str, Any]", kit.get("baseline", {})).items():
        if commands.get(step) != kit_commands.get(step):
            continue
        reader = dict(cast("dict[str, Any]", reader))
        if step == "lint" and commands.get("lint_file") != kit_commands.get(
            "lint_file"
        ):
            reader.pop("file_command", None)
        readers[step] = reader
    readers.update(cast("dict[str, Any]", entry.get("baseline", {})))
    merged.update({k: v for k, v in entry.items() if k not in ("commands", "baseline")})
    merged["commands"] = commands
    if readers:
        merged["baseline"] = readers
    return merged


def kit_dirs() -> list[Path]:
    dirs: list[Path] = []
    try:
        source = locate_source(RECIPES_DIR.parent, os.environ, Path.home())
    except DefaultsError:
        source = None
    if source is not None and source.checkout:
        checkout = source.path / "recipes"
        if checkout.is_dir() and checkout.resolve() != RECIPES_DIR.resolve():
            dirs.append(checkout)
    dirs.append(RECIPES_DIR)
    if source is not None and source.user is not None:
        mine = source.user / USER_RECIPES
        if mine.is_dir():
            dirs.append(mine)
    return dirs


class RecipeBook:
    def __init__(self, drafted: Mapping[str, Recipe] | None = None) -> None:
        self.drafted: dict[str, Recipe] = dict(drafted or {})

    def kit_stacks(self) -> list[str]:
        return sorted({p.stem for d in kit_dirs() for p in d.glob("*.toml")})

    def data(self, stack: str) -> dict[str, Any]:
        """A kit recipe's TOML as written, for an adopted recipe to extend."""
        for folder in kit_dirs():
            path = folder / f"{stack}.toml"
            if path.is_file():
                try:
                    return tomllib.loads(path.read_text())
                except (tomllib.TOMLDecodeError, OSError) as e:
                    raise RecipeError(
                        f"{path}: can't be read ({e}). Fix it, then retry."
                    ) from None
        raise RecipeError(
            f'No kit recipe "{stack}" to extend. Use one of: '
            f"{', '.join(self.kit_stacks())}, or leave out extends and write the "
            "whole recipe."
        )

    def get(self, stack: str) -> Recipe:
        for folder in kit_dirs():
            path = folder / f"{stack}.toml"
            if path.is_file():
                try:
                    data = tomllib.loads(path.read_text())
                    bundled = (RECIPES_DIR / f"{stack}.toml").is_file()
                    older = bundled and folder.resolve() != RECIPES_DIR.resolve()
                    return recipe_from_data(
                        stack,
                        data,
                        str(path),
                        folder,
                        checkout=folder.parent if older else None,
                    )
                except (tomllib.TOMLDecodeError, OSError) as e:
                    raise RecipeError(
                        f"{path}: can't be read ({e}). Fix it, or remove the "
                        f"{stack} recipe from {folder}, then retry."
                    ) from None
        if stack in self.drafted:
            return self.drafted[stack]
        raise RecipeError(
            f'No recipe for stack "{stack}". Use one of: '
            f"{', '.join(self.kit_stacks())}, or draft one with the stack-recipe "
            "skill."
        )


def load_recipe(stack: str) -> Recipe:
    return RecipeBook().get(stack)


def render_template(text: str, name: str, slug: str) -> str:
    values = {"name": name, "slug": slug}
    return _TEMPLATE_VALUE.sub(lambda m: values[m.group(1) or m.group(2)], text)


def check_commands(commands: Mapping[str, str]) -> list[tuple[str, str]]:
    return [(step, commands[step]) for step in CHECK_STEPS if commands.get(step)]


def render_component(
    component: Component, project_slug: str, recipe: Recipe | None = None
) -> dict[str, str]:
    recipe = recipe or load_recipe(component.stack)
    base = Path(component.path)
    return {
        (base / relpath).as_posix(): render_template(text, component.name, project_slug)
        for relpath, text in recipe.templates.items()
    }


def recipe_hash(data: Mapping[str, Any]) -> str:
    content = {k: v for k, v in data.items() if k != "proven_hash"}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
