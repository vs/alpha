import copy
import json
import os
import re
import tempfile
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from alpha import core_areas
from alpha.baseline import (
    BASELINE_STEPS,
    NOT_BASELINED,
    REPO_BASELINED,
    REPO_NOT_BASELINED,
)
from alpha.core_areas import (
    Accessibility,
    Architecture,
    Data,
    Dependencies,
    Errors,
    Observability,
    Performance,
    Releases,
    Security,
    Testing,
    Ui,
)
from alpha.recipes import (
    Recipe,
    RecipeBook,
    adopted_data,
    recipe_from_data,
    recipe_hash,
)
from alpha.render.ci import REPO_JOB
from alpha.validate import (
    NAME,
    as_list,
    boolean,
    choice,
    fail,
    get,
    match_parts,
    obj,
    paths,
    per_component,
    pos_int,
    prefixed,
    sample,
    string,
    strings,
    unmatchable,
)
from alpha.validate import AnswersError as AnswersError

PROJECT_JSON = ".claude/alpha/project.json"
PRINCIPLES_FILE = "docs/principles.toml"
DEPENDENCY_LOG = "docs/dependencies.md"
AREAS: tuple[str, ...] = (
    "identity",
    "components",
    "architecture",
    "errors",
    "testing",
    "ui",
    "documentation",
    "build",
    "security",
    "dependencies",
    "observability",
    "releases",
    "data",
    "accessibility",
    "performance",
    "git",
    "agent_workflow",
)
_COMPONENTS_FIELDS = ("layout", "components_talk", "components", "recipes")


def area_of(where: str) -> str | None:
    head = re.split(r"[.\[]", where, maxsplit=1)[0]
    if head in AREAS:
        return head
    return "components" if head in _COMPONENTS_FIELDS else None


KINDS: frozenset[str] = frozenset(
    {"backend", "frontend", "cli", "mobile", "ml", "library", "worker"}
)
_UI_KINDS = frozenset({"frontend", "mobile"})
LICENSES: frozenset[str] = frozenset({"MIT", "Apache-2.0", "Proprietary"})
EXTERNAL_DOCS: tuple[str, ...] = ("readme", "folder", "elsewhere", "none")
CI_PROVIDERS: tuple[str, ...] = ("github-actions", "none")
ARTIFACTS: tuple[str, ...] = (
    "none",
    "package",
    "container",
    "static-site",
    "binary",
    "app",
    "other",
)
_STATUSES = ("done", "in_progress", "pending")
_LAYOUTS = ("monorepo", "single")
_CHANGES = ("tighten", "loosen", "drop")
_REVIEW_MODES = ("at-merge", "batched", "every-task")
_SCOPE = re.compile(r"[a-z0-9-]+")
_TRAITS = (
    "has_ui",
    "deployed",
    "network_calls",
    "persisted_data",
    "ml",
    "nontrivial_logic",
)
_TOP_KEYS = frozenset(
    {
        "schema",
        "areas",
        "identity",
        "layout",
        "components_talk",
        "components",
        "git",
        "agent_workflow",
        "architecture",
        "errors",
        "testing",
        "documentation",
        "build",
        "security",
        "dependencies",
        "observability",
        "ui",
        "releases",
        "data",
        "accessibility",
        "performance",
        "overrides",
        "decisions",
        "recipes",
        "manifest",
        "adoption",
    }
)


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    acceptance: str


@dataclass(frozen=True)
class Identity:
    name: str
    slug: str
    value_proposition: str
    target_users: str
    requirements: tuple[Requirement, ...]
    license: str
    license_file: str | None
    copyright_holder: str
    domain_jargon: bool


@dataclass(frozen=True)
class Traits:
    has_ui: bool
    deployed: bool
    network_calls: bool
    persisted_data: bool
    ml: bool
    nontrivial_logic: bool


@dataclass(frozen=True)
class Component:
    name: str
    path: str
    kind: str
    stack: str
    traits: Traits

    @property
    def has_ui(self) -> bool:
        return self.kind in _UI_KINDS or self.traits.has_ui


@dataclass(frozen=True)
class GitPrefs:
    convention: str
    scopes: tuple[str, ...]
    branching: str


@dataclass(frozen=True)
class AgentWorkflow:
    review_mode: str
    max_lines: int
    max_files: int
    extra_risk_paths: tuple[str, ...]


@dataclass(frozen=True)
class DocMapping:
    paths: tuple[str, ...]
    docs: tuple[str, ...]


@dataclass(frozen=True)
class Documentation:
    external: str
    external_path: str
    external_location: str
    mappings: tuple[DocMapping, ...]


@dataclass(frozen=True)
class BuildTarget:
    name: str
    artifact: str
    hosting: str


@dataclass(frozen=True)
class Build:
    ci: str
    environments: tuple[str, ...]
    components: tuple[BuildTarget, ...]


@dataclass(frozen=True)
class Override:
    principle: str
    scope: str
    change: str
    params: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class Decision:
    area: str
    title: str
    context: str
    decision: str
    consequences: str


PHASES = ("P0", "P1", "P2", "P3", "P4", "P5", "P6")
STEP_STATUSES = ("pending", "in_progress", "done", "dropped")
CONDITIONS = ("run", "recipe", "no_baseline", "commit_hook", "confirm")
_STEP_KEYS = frozenset(
    {
        "id",
        "phase",
        "title",
        "why",
        "component",
        "principles",
        "depends_on",
        "acceptance",
        "status",
        "branch",
        "decision",
    }
)


@dataclass(frozen=True)
class Condition:
    """One part of a step's acceptance (spec §5b): `kind` is one of
    CONDITIONS; `value` is its command, recipe field, check id or text."""

    kind: str
    value: str
    dir: str = "."


def describe_condition(c: Condition) -> str:
    if c.kind == "run":
        where = "" if c.dir == "." else f" (in {c.dir})"
        return f"`{c.value}` passes{where}"
    if c.kind == "recipe":
        return f"the recipe sets {c.value}"
    if c.kind == "no_baseline":
        return f"{c.value} is no longer baselined (not in adoption.baselines)"
    if c.kind == "commit_hook":
        return "git's commit-msg hook runs alpha's commit check"
    return f"the user confirms: {c.value}"


@dataclass(frozen=True)
class Step:
    """A step of an adopted repo's compliance plan (spec §5b, step 6)."""

    id: str
    phase: str
    title: str
    why: str
    component: str | None
    principles: tuple[str, ...]
    depends_on: tuple[str, ...]
    acceptance: tuple[Condition, ...]
    status: str
    branch: str | None
    decision: int | None


@dataclass(frozen=True)
class Answers:
    schema: int
    areas: dict[str, str]
    identity: Identity | None
    layout: str | None
    components_talk: bool
    components: tuple[Component, ...]
    git: GitPrefs | None
    agent_workflow: AgentWorkflow | None
    architecture: Architecture | None
    errors: Errors | None
    testing: Testing | None
    documentation: Documentation | None
    build: Build | None
    security: Security | None
    dependencies: Dependencies | None
    observability: Observability | None
    ui: Ui | None
    releases: Releases | None
    data: Data | None
    accessibility: Accessibility | None
    performance: Performance | None
    overrides: tuple[Override, ...]
    decisions: tuple[Decision, ...]
    recipes: dict[str, Recipe]
    # Checks that run through the ratchet (spec §8b): `<step>:<component>` or
    # a repository check id. Only an adopted project has any.
    baselines: tuple[str, ...] = ()
    # Who runs git's hooks in an adopted repo: alpha ("alpha"), or the repo's
    # own hook manager, which calls alpha's commit-msg check ("chain").
    git_hooks: str | None = None
    # The repo's hook-manager files the survey found, where a chained commit-msg
    # hook calls alpha's check.
    hook_files: tuple[str, ...] = ()
    # The compliance plan of an adopted repo, in order.
    steps: tuple["Step", ...] = ()

    def book(self) -> RecipeBook:
        return RecipeBook(self.recipes)


def drafted_recipes(
    raw: object, require_proven: bool = False, generated: bool = False
) -> dict[str, Recipe]:
    kit = set(RecipeBook().kit_stacks())
    drafted: dict[str, Recipe] = {}
    for stack, data in obj(raw, "recipes").items():
        where = f"recipes.{stack}"
        if not NAME.fullmatch(stack):
            raise fail(
                where,
                f"{stack!r} isn't a valid stack name",
                "Use lowercase letters, digits and hyphens, e.g. rust",
            )
        fields = obj(data, where)
        if stack in kit and fields.get("adopted") is True:
            raise fail(
                where,
                f"an adopted recipe can't take the kit's {stack!r} name",
                f'Name it after the component, e.g. "api-{stack}", and set that '
                "as the component's stack",
            )
        if stack in kit and generated:
            continue
        if stack in kit:
            raise fail(
                where,
                f"the kit already has a {stack} recipe",
                "Remove this one; the kit's recipe is used",
            )
        if "proven" in fields:
            raise fail(
                f"{where}.proven",
                "is set, but a drafted recipe is always less proven than the kit's",
                'Remove "proven"; alpha marks drafted recipes itself',
            )
        resolved: Mapping[str, Any] = fields
        base = fields.get("extends")
        if base is not None and fields.get("adopted") is True:
            if not isinstance(base, str) or base not in kit:
                raise fail(
                    f"{where}.extends",
                    f"{base!r} isn't a kit recipe",
                    f"Use one of: {', '.join(sorted(kit))}, or leave extends out",
                )
            resolved = adopted_data(fields, RecipeBook().data(base))
        drafted[stack] = recipe_from_data(
            stack, resolved, where, None, generated=generated
        )
        if require_proven and fields.get("proven_hash") != recipe_hash(fields):
            raise fail(
                where,
                "not proven since it last changed",
                f'Run "alpha recipe try <target> {stack}" until it prints ok, or '
                "remove it from recipes if no component uses it",
            )
    return drafted


def _project_root(answers_path: Path) -> Path:
    return answers_path.resolve().parent.parent.parent


def _identity(raw: object, base: Path) -> Identity:
    where = "identity"
    d = obj(raw, where)
    slug = string(d, "slug", where)
    if not NAME.fullmatch(slug):
        raise fail(
            "identity.slug",
            f"{slug!r} is not a valid slug",
            "Use lowercase letters, digits and hyphens, starting with a letter",
        )
    reqs: list[Requirement] = []
    for i, r in enumerate(
        as_list(get(d, "requirements", where), "identity.requirements")
    ):
        rw = f"identity.requirements[{i}]"
        ro = obj(r, rw)
        reqs.append(
            Requirement(
                string(ro, "id", rw),
                string(ro, "text", rw),
                string(ro, "acceptance", rw),
            )
        )
    license_file = d.get("license_file")
    if license_file is not None and not isinstance(license_file, str):
        raise fail("identity.license_file", "must be a path or null", "Use a path")
    license_ = string(d, "license", where)
    if license_file is not None:
        relative = PurePosixPath(license_file)
        if relative.is_absolute() or ".." in relative.parts:
            raise fail(
                "identity.license_file",
                f"{license_file!r} is outside the project",
                "Copy the license text into the project (e.g. LICENSE) and give "
                "its path relative to the project root",
            )
        resolved = base / license_file
        if not resolved.is_file():
            raise fail(
                "identity.license_file",
                f"{resolved} does not exist",
                "Point it at an existing file, or set it to null and pick MIT, "
                "Apache-2.0 or Proprietary",
            )
    elif license_ not in LICENSES:
        raise fail(
            "identity.license",
            f"{license_!r} is not a built-in license",
            "Use MIT, Apache-2.0 or Proprietary, "
            "or set license_file to your own license text",
        )
    return Identity(
        name=string(d, "name", where),
        slug=slug,
        value_proposition=string(d, "value_proposition", where),
        target_users=string(d, "target_users", where),
        requirements=tuple(reqs),
        license=license_,
        license_file=license_file,
        copyright_holder=string(d, "copyright_holder", where),
        domain_jargon=boolean(d, "domain_jargon", where),
    )


def _component(raw: object, i: int, stacks: set[str], drafted: set[str]) -> Component:
    where = f"components[{i}]"
    d = obj(raw, where)
    name = string(d, "name", where)
    if not NAME.fullmatch(name):
        raise fail(
            f"{where}.name",
            f"{name!r} is not a valid name",
            "Use lowercase letters, digits and hyphens, starting with a letter",
        )
    if name == REPO_JOB:
        raise fail(
            f"{where}.name",
            f"{name!r} is reserved: the CI job that runs the repository checks "
            "has that name, and a component's job would replace it",
            'Give the component another name, such as "repo-tools"',
        )
    path = string(d, "path", where)
    if path != "." and unmatchable(path):
        raise fail(
            f"{where}.path",
            f"{path!r} must be relative to the project root",
            'Use a folder like "api" or "apps/api": no leading "/" or "./", '
            'no trailing "/", no ".." or "//"',
        )
    stack = string(d, "stack", where)
    if stack not in stacks:
        kit = ", ".join(sorted(stacks - drafted))
        raise fail(
            f"{where}.stack",
            f'"{stack}" has no recipe',
            f"Draft one with the stack-recipe skill, or use one of: {kit}",
        )
    tw = f"{where}.traits"
    t = obj(get(d, "traits", where), tw)
    traits = Traits(**{k: boolean(t, k, tw) for k in _TRAITS})
    return Component(name, path, choice(d, "kind", where, sorted(KINDS)), stack, traits)


def _components(raw: object, layout: str, book: RecipeBook) -> tuple[Component, ...]:
    stacks = {*book.kit_stacks(), *book.drafted}
    drafted = set(book.drafted)
    comps = [
        _component(c, i, stacks, drafted)
        for i, c in enumerate(as_list(raw, "components"))
    ]
    if not comps:
        raise fail("components", "is empty", "Add at least one component")
    seen: dict[str, int] = {}
    for i, c in enumerate(comps):
        if c.name in seen:
            raise fail(
                f"components[{i}].name",
                f"duplicate name {c.name!r} (also components[{seen[c.name]}])",
                "Give each component its own name",
            )
        seen[c.name] = i
    if layout == "single":
        if len(comps) != 1:
            raise fail(
                "layout",
                f"single needs exactly one component, found {len(comps)}",
                'Set layout to "monorepo", or remove components',
            )
        if comps[0].path != ".":
            raise fail(
                "components[0].path",
                f"is {comps[0].path!r} but layout is single",
                'Set path to "." or change layout to "monorepo"',
            )
    for i, c in enumerate(comps):
        for j, o in enumerate(comps[:i]):
            a, b = PurePosixPath(c.path).parts, PurePosixPath(o.path).parts
            if a[: len(b)] == b or b[: len(a)] == a:
                inner, outer = (i, j) if len(a) >= len(b) else (j, i)
                raise fail(
                    f"components[{inner}].path",
                    f"{comps[inner].path!r} is inside (or equal to) "
                    f"components[{outer}].path {comps[outer].path!r}",
                    "Give each component its own folder, not nested in another",
                )
    return tuple(comps)


def _git(raw: object) -> GitPrefs:
    d = obj(raw, "git")
    scopes = strings(d, "scopes", "git")
    for i, scope in enumerate(scopes):
        if not _SCOPE.fullmatch(scope):
            raise fail(
                f"git.scopes[{i}]",
                f"{scope!r} can't be a commit scope",
                "Use only lowercase letters, digits and hyphens, e.g. "
                '"api" or "deps"; the commit-msg hook rejects anything else',
            )
    return GitPrefs(
        string(d, "convention", "git"), scopes, string(d, "branching", "git")
    )


def _workflow(raw: object) -> AgentWorkflow:
    w = "agent_workflow"
    d = obj(raw, w)
    return AgentWorkflow(
        choice(d, "review_mode", w, _REVIEW_MODES),
        pos_int(d, "max_lines", w),
        pos_int(d, "max_files", w),
        strings(d, "extra_risk_paths", w),
    )


def _documentation(raw: object) -> Documentation:
    w = "documentation"
    d = obj(raw, w)
    external = choice(d, "external", w, EXTERNAL_DOCS)
    path = string(d, "external_path", w, blank=True)
    location = string(d, "external_location", w, blank=True)
    if external == "folder":
        parts = path.split("/")
        if unmatchable(path) or len(parts) < 2 or parts[0] != "docs":
            raise fail(
                "documentation.external_path",
                f"{path!r} is not a folder under docs/",
                'Use a folder inside docs/, e.g. "docs/guide"',
            )
        if parts[1] == "decisions" or parts[-1].endswith((".md", ".toml")):
            raise fail(
                "documentation.external_path",
                f"{path!r} is where alpha writes its own docs (docs/*.md, "
                "docs/principles.toml, docs/decisions/)",
                'Use a folder of its own, e.g. "docs/guide"',
            )
    elif path:
        raise fail(
            "documentation.external_path",
            f"is {path!r} but external docs are {external!r}",
            'Set it to "" (only the folder choice has a path)',
        )
    if external == "elsewhere" and not location.strip():
        raise fail(
            "documentation.external_location",
            "is empty but external docs live elsewhere",
            "Say where, e.g. a wiki URL",
        )
    if external != "elsewhere" and location:
        raise fail(
            "documentation.external_location",
            f"is {location!r} but external docs are {external!r}",
            'Set it to "" (only the elsewhere choice has a location)',
        )
    mappings: list[DocMapping] = []
    for i, m in enumerate(as_list(get(d, "mappings", w), "documentation.mappings")):
        mw = f"documentation.mappings[{i}]"
        mo = obj(m, mw)
        mappings.append(DocMapping(paths(mo, "paths", mw), paths(mo, "docs", mw)))
    return Documentation(external, path, location, tuple(mappings))


def _build(
    raw: object, comps: tuple[Component, ...] | None, overrides: tuple[Override, ...]
) -> Build:
    w = "build"
    d = obj(raw, w)
    ci = choice(d, "ci", w, CI_PROVIDERS)
    if ci == "none" and not any(
        o.principle == "build-hosting-upfront"
        and o.scope == "project"
        and o.change in ("loosen", "drop")
        for o in overrides
    ):
        raise fail(
            "build.ci",
            "is none, which loosens the build-hosting-upfront principle",
            "Add an override loosening build-hosting-upfront with the reason "
            "there is no CI",
        )
    environments = strings(d, "environments", w)
    for i, env in enumerate(environments):
        if not NAME.fullmatch(env):
            raise fail(
                f"build.environments[{i}]",
                f"{env!r} is not a valid environment name",
                "Use lowercase letters, digits and hyphens, e.g. production",
            )
    targets: list[BuildTarget] = []
    for i, t in enumerate(as_list(get(d, "components", w), "build.components")):
        tw = f"build.components[{i}]"
        to = obj(t, tw)
        targets.append(
            BuildTarget(
                string(to, "name", tw),
                choice(to, "artifact", tw, ARTIFACTS),
                string(to, "hosting", tw, blank=True),
            )
        )
    if comps is not None:
        per_component(targets, comps, "build.components", ("artifact", "hosting"))
        by_name = {c.name: c for c in comps}
        for i, t in enumerate(targets):
            if by_name[t.name].traits.deployed and not t.hosting.strip():
                raise fail(
                    f"build.components[{i}].hosting",
                    f"component {t.name!r} is deployed but has no hosting",
                    "Say where it runs, e.g. a cloud service or your own servers",
                )
        if not environments and any(c.traits.deployed for c in comps):
            raise fail(
                "build.environments",
                "is empty but a component is deployed",
                'Name at least one environment, e.g. ["production"]',
            )
    return Build(ci, environments, tuple(targets))


def _check_protected(
    security: Security,
    comps: tuple[Component, ...],
    documentation: Documentation | None,
    book: RecipeBook,
) -> None:
    needed = [(p, p) for p in (PRINCIPLES_FILE, DEPENDENCY_LOG)]
    if documentation is not None:
        needed += [(d, d) for m in documentation.mappings for d in m.docs]
    for c in comps:
        recipe = book.get(c.stack)
        needed += [(m, m) for m in (prefixed(c.path, m) for m in recipe.manifests)]
        needed += [
            (f"{t} (tests)", sample(t))
            for t in (prefixed(c.path, g) for g in recipe.test_globs)
        ]
    for i, glob in enumerate(security.extra_protected):
        for shown, path in needed:
            if match_parts(path.split("/"), glob.split("/")):
                raise fail(
                    f"security.extra_protected[{i}]",
                    f"{glob!r} covers {shown}, which alpha's checks may require "
                    "changing",
                    f"Protect something narrower: alpha's checks must be able to "
                    f"change {shown}",
                )


def _override(raw: object, i: int, names: set[str] | None) -> Override:
    where = f"overrides[{i}]"
    d = obj(raw, where)
    change = choice(d, "change", where, _CHANGES)
    scope = string(d, "scope", where)
    if scope != "project":
        name = (
            scope.removeprefix("component:") if scope.startswith("component:") else None
        )
        if name is None:
            raise fail(
                f"{where}.scope",
                f"{scope!r} is not a valid scope",
                'Use "project" or "component:<name>"',
            )
        if names is not None and name not in names:
            raise fail(
                f"{where}.scope",
                f"there is no component named {name!r}",
                f"Use one of: {', '.join(sorted(names)) or '(none)'}",
            )
    reason = d.get("reason", "")
    if not isinstance(reason, str):
        raise fail(f"{where}.reason", "must be text", "Write the reason as a string")
    if change in ("loosen", "drop") and not reason.strip():
        raise fail(
            f"{where}.reason",
            f"a reason is required when you {change} a principle",
            "Explain why this project is an exception",
        )
    params = d.get("params", {})
    return Override(
        string(d, "principle", where),
        scope,
        change,
        dict(obj(params, f"{where}.params")),
        reason,
    )


def _decision(raw: object, i: int) -> Decision:
    where = f"decisions[{i}]"
    d = obj(raw, where)
    return Decision(
        choice(d, "area", where, AREAS),
        string(d, "title", where),
        string(d, "context", where),
        string(d, "decision", where),
        string(d, "consequences", where),
    )


_ADOPTION_KEYS = ("baselines", "survey", "git_hooks", "steps")
GIT_HOOKS = ("alpha", "chain")


def _baseline_id(
    check: object, where: str, comps: tuple[Component, ...] | None, book: RecipeBook
) -> str:
    if not isinstance(check, str) or not check:
        raise fail(where, "must be a check id", 'Write e.g. "typecheck:api" or "typos"')
    step, sep, name = check.partition(":")
    if not sep:
        if check in REPO_NOT_BASELINED:
            raise fail(
                where,
                f"{check} can't be baselined: {REPO_NOT_BASELINED[check]}",
                "Remove it",
            )
        if check not in REPO_BASELINED:
            raise fail(
                where,
                f"{check!r} isn't a check a baseline can hold",
                "Use <step>:<component> (steps: "
                f"{', '.join(BASELINE_STEPS)}) or one of: {', '.join(REPO_BASELINED)}",
            )
        return check
    if step in NOT_BASELINED:
        raise fail(
            where, f"{step} can't be baselined: {NOT_BASELINED[step]}", "Remove it"
        )
    if step not in BASELINE_STEPS:
        raise fail(
            where,
            f"{step!r} isn't a step a baseline can hold",
            f"Use one of: {', '.join(BASELINE_STEPS)}",
        )
    if comps is None:
        return check
    comp = next((c for c in comps if c.name == name), None)
    if comp is None:
        raise fail(
            where,
            f"no component named {name!r}",
            f"Use one of: {', '.join(c.name for c in comps)}",
        )
    if step not in book.get(comp.stack).baselines:
        raise fail(
            where,
            f"the {comp.stack} recipe has no [baseline.{step}], so alpha can't read "
            f"its {step} findings",
            f"Add [baseline.{step}] to the recipe (the stack-recipe skill), or remove "
            "this entry",
        )
    return check


def _hook_files(raw: object) -> tuple[str, ...]:
    survey: object = obj(raw, "adoption").get("survey", {})
    git: object = (
        cast(dict[str, Any], survey).get("git", {}) if isinstance(survey, dict) else {}
    )
    found: object = (
        cast(dict[str, Any], git).get("hook_managers", [])
        if isinstance(git, dict)
        else []
    )
    items = cast(list[object], found) if isinstance(found, list) else []
    return tuple(str(f) for f in items if isinstance(f, str))


def _git_hooks(raw: object) -> str | None:
    d = obj(raw, "adoption")
    return choice(d, "git_hooks", "adoption", GIT_HOOKS) if "git_hooks" in d else None


def _adoption(
    raw: object, comps: tuple[Component, ...] | None, book: RecipeBook
) -> tuple[str, ...]:
    d = obj(raw, "adoption")
    for key in d:
        if key not in _ADOPTION_KEYS:
            raise fail(
                f"adoption.{key}",
                "unknown key",
                f"Remove it; allowed keys are {', '.join(_ADOPTION_KEYS)}",
            )
    obj(d.get("survey", {}), "adoption.survey")  # alpha adopt survey writes it
    checks = as_list(d.get("baselines", []), "adoption.baselines")
    out: list[str] = []
    for i, check in enumerate(checks):
        where = f"adoption.baselines[{i}]"
        found = _baseline_id(check, where, comps, book)
        if found in out:
            raise fail(where, f"{found} is listed twice", "Remove one")
        out.append(found)
    return tuple(out)


def _condition(
    raw: object, where: str, comps: tuple[Component, ...] | None, book: RecipeBook
) -> Condition:
    d = obj(raw, where)
    kinds = [k for k in d if k in CONDITIONS]
    extra = [k for k in d if k not in CONDITIONS and k != "dir"]
    if len(kinds) != 1 or extra:
        raise fail(
            where,
            "must name exactly one condition",
            f"Use one of {', '.join(CONDITIONS)}, e.g. "
            '{"run": "mise run check:component:api"}',
        )
    kind = kinds[0]
    if kind == "commit_hook":
        if d[kind] is not True:
            raise fail(f"{where}.commit_hook", "must be true", "Write true")
        return Condition(kind, "")
    value = string(d, kind, where)
    if "dir" in d and kind != "run":
        raise fail(f"{where}.dir", "only goes with run", "Remove it")
    folder = string(d, "dir", where) if "dir" in d else "."
    if kind == "recipe" and comps is not None:
        name, _, field_ = value.partition(".")
        comp = next((c for c in comps if c.name == name), None)
        if comp is None:
            raise fail(
                f"{where}.recipe",
                f"no component named {name!r}",
                f"Use <component>.<field> with one of: "
                f"{', '.join(c.name for c in comps)}",
            )
        group, _, step = field_.partition(".")
        known = field_ == "coverage" or (
            group == "commands" and step in book.get(comp.stack).commands
        )
        if not known:
            raise fail(
                f"{where}.recipe",
                f"{field_!r} isn't a recipe field alpha can check",
                "Use commands.<step> (e.g. commands.typecheck) or coverage",
            )
    return Condition(kind, value, folder)


def _steps(
    raw: object, comps: tuple[Component, ...] | None, book: RecipeBook
) -> tuple[Step, ...]:
    d = obj(raw, "adoption")
    steps: list[Step] = []
    for i, entry in enumerate(as_list(d.get("steps", []), "adoption.steps")):
        where = f"adoption.steps[{i}]"
        e = obj(entry, where)
        for key in e:
            if key not in _STEP_KEYS:
                raise fail(
                    f"{where}.{key}",
                    "unknown key",
                    f"Use only: {', '.join(sorted(_STEP_KEYS))}",
                )
        sid = string(e, "id", where)
        if not NAME.fullmatch(sid):
            raise fail(
                f"{where}.id",
                f"{sid!r} isn't a lowercase id with hyphens",
                'Write e.g. "p2-typecheck-api"',
            )
        if any(s.id == sid for s in steps):
            raise fail(f"{where}.id", f"{sid} is used twice", "Rename one")
        known = {s.id for s in steps}
        depends = strings(e, "depends_on", where) if "depends_on" in e else ()
        for dep in depends:
            if dep not in known:
                raise fail(
                    f"{where}.depends_on",
                    f"{dep!r} isn't a step listed before this one",
                    "List a step after the steps it depends on",
                )
        component = string(e, "component", where) if "component" in e else None
        if component is not None and comps is not None:
            if component not in {c.name for c in comps}:
                raise fail(
                    f"{where}.component",
                    f"no component named {component!r}",
                    f"Use one of: {', '.join(c.name for c in comps)}",
                )
        acceptance = tuple(
            _condition(c, f"{where}.acceptance[{j}]", comps, book)
            for j, c in enumerate(
                as_list(get(e, "acceptance", where), f"{where}.acceptance")
            )
        )
        if not acceptance:
            raise fail(
                f"{where}.acceptance",
                "is empty",
                "Name what proves the step done, e.g. a command that must pass",
            )
        status = choice(e, "status", where, STEP_STATUSES)
        decision: int | None = None
        if "decision" in e:
            decision = pos_int(e, "decision", where)
        if status == "dropped" and decision is None:
            raise fail(
                f"{where}.decision",
                "is missing for a dropped step",
                "Drop it with alpha adopt drop, which records the decision",
            )
        steps.append(
            Step(
                id=sid,
                phase=choice(e, "phase", where, PHASES),
                title=string(e, "title", where),
                why=string(e, "why", where),
                component=component,
                principles=strings(e, "principles", where) if "principles" in e else (),
                depends_on=depends,
                acceptance=acceptance,
                status=status,
                branch=string(e, "branch", where) if "branch" in e else None,
                decision=decision,
            )
        )
    return tuple(steps)


def generated_components(applied: Mapping[str, Any]) -> set[str]:

    def entries(key: str) -> list[Mapping[str, object]]:
        raw: object = applied.get(key)
        items = cast(list[object], raw) if isinstance(raw, list) else []
        return [cast(Mapping[str, object], e) for e in items if isinstance(e, dict)]

    names = {n for c in entries("components") if isinstance(n := c.get("name"), str)}
    for o in entries("overrides"):
        scope = o.get("scope")
        if isinstance(scope, str) and scope.startswith("component:"):
            names.add(scope.removeprefix("component:"))
    return names


def _generated_components(top: Mapping[str, Any]) -> set[str]:
    manifest: object = top.get("manifest")
    if not isinstance(manifest, dict):
        return set()
    applied: object = cast(dict[str, object], manifest).get("applied")
    if not isinstance(applied, dict):
        return set()
    return generated_components(cast(dict[str, Any], applied))


def answers_snapshot(top: Mapping[str, Any]) -> dict[str, Any]:
    return {k: copy.deepcopy(v) for k, v in top.items() if k != "manifest"}


def load_answers(path: Path, require_areas: Sequence[str] = AREAS) -> Answers:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        raise fail(
            str(path),
            "file not found or unreadable",
            "Run the alpha interview first, or pass the right path",
        ) from None
    except UnicodeDecodeError:
        raise fail(
            str(path),
            "is not UTF-8 text",
            "Save it as UTF-8, or delete it and run the alpha interview again",
        ) from None
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as e:
        raise fail(
            str(path), f"not valid JSON ({e.msg} at line {e.lineno})", "Fix the syntax"
        ) from None
    top = obj(data, str(path))
    return parse_answers(top, _project_root(path), require_areas)


def parse_answers(
    top: Mapping[str, Any],
    base: Path,
    require_areas: Sequence[str] = AREAS,
    generated: bool | None = None,
    former: Collection[str] = (),
) -> Answers:
    for key in top:
        if key not in _TOP_KEYS:
            raise fail(
                key,
                "unknown key",
                f"Remove it; allowed keys are {', '.join(sorted(_TOP_KEYS))}",
            )
    for area in require_areas:
        if area not in AREAS:
            raise fail(
                "area", f"{area!r} is not an area", f"Use one of: {', '.join(AREAS)}"
            )
    schema = get(top, "schema", "")
    if schema != 1:
        raise fail("schema", f"{schema!r} is not supported", "Set schema to 1")
    areas_raw = obj(get(top, "areas", ""), "areas")
    areas: dict[str, str] = {
        a: choice(areas_raw, a, "areas", _STATUSES) if a in areas_raw else "pending"
        for a in AREAS
    }
    for area in require_areas:
        if areas[area] != "done":
            raise fail(
                f"areas.{area}",
                f"is {areas[area]}, not done",
                f"Finish the {area} part of the interview, then retry",
            )

    def active(area: str) -> bool:
        return area in require_areas or areas[area] == "done"

    drafted = drafted_recipes(
        top.get("recipes", {}),
        require_proven=active("components"),
        generated="manifest" in top if generated is None else generated,
    )
    identity = _identity(get(top, "identity", ""), base) if active("identity") else None
    layout: str | None = None
    comps: tuple[Component, ...] = ()
    if active("components"):
        layout = choice(top, "layout", "", _LAYOUTS)
        comps = _components(get(top, "components", ""), layout, RecipeBook(drafted))
    git = _git(get(top, "git", "")) if active("git") else None
    workflow = (
        _workflow(get(top, "agent_workflow", "")) if active("agent_workflow") else None
    )
    names = (
        {c.name for c in comps} | set(former) | _generated_components(top)
        if active("components")
        else None
    )
    overrides = tuple(
        _override(o, i, names)
        for i, o in enumerate(as_list(top.get("overrides", []), "overrides"))
    )
    talk = top.get("components_talk", False)
    if not isinstance(talk, bool):
        raise fail("components_talk", "must be true or false", "Use true or false")
    if talk and active("components") and len(comps) == 1:
        raise fail(
            "components_talk",
            "is true but there is only one component",
            "Set components_talk to false",
        )
    comps_or_none = comps if active("components") else None
    jargon = identity.domain_jargon if identity else False
    architecture = (
        core_areas.architecture(
            get(top, "architecture", ""), comps_or_none, talk, jargon
        )
        if active("architecture")
        else None
    )
    errors = (
        core_areas.errors(get(top, "errors", ""), comps_or_none)
        if active("errors")
        else None
    )
    testing = (
        core_areas.testing(get(top, "testing", ""), comps_or_none, talk)
        if active("testing")
        else None
    )
    documentation = (
        _documentation(get(top, "documentation", ""))
        if active("documentation")
        else None
    )
    build = (
        _build(
            get(top, "build", ""), comps if active("components") else None, overrides
        )
        if active("build")
        else None
    )
    security = (
        core_areas.security(get(top, "security", ""), comps_or_none)
        if active("security")
        else None
    )
    if security is not None and active("components"):
        _check_protected(security, comps, documentation, RecipeBook(drafted))
    dependencies = (
        core_areas.dependencies(get(top, "dependencies", ""))
        if active("dependencies")
        else None
    )
    observability = (
        core_areas.observability(get(top, "observability", ""), comps_or_none)
        if active("observability")
        else None
    )
    ui = core_areas.ui(get(top, "ui", ""), comps_or_none) if active("ui") else None
    releases = (
        core_areas.releases(get(top, "releases", ""), comps_or_none)
        if active("releases")
        else None
    )
    data_area = (
        core_areas.data(get(top, "data", ""), comps_or_none) if active("data") else None
    )
    accessibility = (
        core_areas.accessibility(get(top, "accessibility", ""), comps_or_none)
        if active("accessibility")
        else None
    )
    performance = (
        core_areas.performance(get(top, "performance", ""), comps_or_none)
        if active("performance")
        else None
    )
    decisions = tuple(
        _decision(x, i)
        for i, x in enumerate(as_list(top.get("decisions", []), "decisions"))
    )
    baselines = _adoption(top.get("adoption", {}), comps_or_none, RecipeBook(drafted))
    have = {d.area for d in decisions}
    for area in AREAS:
        if areas[area] == "done" and area not in have:
            raise fail(
                "decisions",
                f"no decision recorded for the done area {area!r}",
                f'Add a decision with "area": "{area}" '
                "(title, context, decision, consequences)",
            )
    return Answers(
        1,
        areas,
        identity,
        layout,
        talk,
        comps,
        git,
        workflow,
        architecture,
        errors,
        testing,
        documentation,
        build,
        security,
        dependencies,
        observability,
        ui,
        releases,
        data_area,
        accessibility,
        performance,
        overrides,
        decisions,
        drafted,
        baselines,
        _git_hooks(top.get("adoption", {})),
        _hook_files(top.get("adoption", {})),
        _steps(top.get("adoption", {}), comps_or_none, RecipeBook(drafted)),
    )


def write_answers(target: Path, text: str) -> Path:
    try:
        update: object = json.loads(text)
    except json.JSONDecodeError as e:
        raise fail(
            "input",
            f"not valid JSON ({e.msg} at line {e.lineno})",
            "Fix the syntax: pass one object on one line in single quotes, "
            "writing each ' inside it as '\\''",
        ) from None
    if not isinstance(update, dict):
        raise fail(
            "input",
            f"expected a JSON object, got {type(update).__name__}",
            'Send the keys to save as one object, e.g. {"layout": "single"}',
        )
    for key in cast(dict[str, Any], update):
        if key == "manifest":
            raise fail(
                key,
                "is written by alpha generate, not by the interview",
                "Leave it out",
            )
        if key not in _TOP_KEYS:
            raise fail(
                key,
                "unknown key",
                f"Remove it; allowed keys are "
                f"{', '.join(sorted(_TOP_KEYS - {'manifest'}))}",
            )
    path = target / PROJECT_JSON
    data: dict[str, Any] = {}
    if path.exists():
        try:
            current: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:  # ValueError: bad JSON or not UTF-8
            raise fail(
                str(path),
                f"can't merge into it, it's not valid JSON ({e})",
                "Fix the file by hand, or delete it to start the interview over",
            ) from None
        if not isinstance(current, dict):
            raise fail(
                str(path),
                "can't merge into it, it's not a JSON object",
                "Fix the file by hand, or delete it to start the interview over",
            )
        data = cast(dict[str, Any], current)
    data.update(cast(dict[str, Any], update))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".project.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            # mkstemp makes the file owner-only; keep the mode the file had,
            # or the one any other new file would get.
            os.chmod(tmp, _mode_for(path))
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError as e:
        raise fail(
            str(path),
            f"could not save it ({e.strerror or e})",
            "Check the folder's permissions and free space, then retry",
        ) from None
    return path


def _mode_for(path: Path) -> int:
    if path.exists():
        return path.stat().st_mode & 0o777
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask
