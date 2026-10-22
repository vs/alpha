"""Interview answers (.claude/alpha/project.json): model and validation."""

import json
import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from alpha import core_areas
from alpha.core_areas import Architecture, Errors, Testing
from alpha.validate import (
    NAME,
    as_list,
    boolean,
    choice,
    fail,
    get,
    obj,
    paths,
    per_component,
    pos_int,
    string,
    strings,
    unmatchable,
)
from alpha.validate import AnswersError as AnswersError  # re-exported for callers

PROJECT_JSON = ".claude/alpha/project.json"
AREAS: tuple[str, ...] = (
    "identity",
    "components",
    "architecture",
    "errors",
    "testing",
    "documentation",
    "build",
    "git",
    "agent_workflow",
)
KINDS: frozenset[str] = frozenset(
    {"backend", "frontend", "cli", "mobile", "ml", "library", "worker"}
)
STACKS: frozenset[str] = frozenset({"python", "typescript"})
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
_REVIEW_MODES = ("batched", "every-task")
_SCOPE = re.compile(r"[a-z0-9-]+")  # what the commit-msg hook accepts
_TRAITS = (
    "has_ui",
    "deployed",
    "network_calls",
    "persisted_data",
    "ml",
    "nontrivial_logic",
)
# "manifest" is written by alpha generate (the file hashes), not by the interview.
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
        "overrides",
        "decisions",
        "manifest",
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
    overrides: tuple[Override, ...]
    decisions: tuple[Decision, ...]


def _project_root(answers_path: Path) -> Path:
    """Project root for an answers file at <root>/.claude/alpha/project.json."""
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
        resolved = base / license_file  # an absolute license_file wins
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


def _component(raw: object, i: int) -> Component:
    where = f"components[{i}]"
    d = obj(raw, where)
    name = string(d, "name", where)
    if not NAME.fullmatch(name):
        raise fail(
            f"{where}.name",
            f"{name!r} is not a valid name",
            "Use lowercase letters, digits and hyphens, starting with a letter",
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
    if stack not in STACKS:
        raise fail(
            f"{where}.stack",
            f"{stack} is not supported yet; alpha 0.1 supports python and typescript",
            "Pick one, or wait for the generic-stack recipe (plan 2)",
        )
    tw = f"{where}.traits"
    t = obj(get(d, "traits", where), tw)
    traits = Traits(**{k: boolean(t, k, tw) for k in _TRAITS})
    return Component(name, path, choice(d, "kind", where, sorted(KINDS)), stack, traits)


def _components(raw: object, layout: str) -> tuple[Component, ...]:
    comps = [_component(c, i) for i, c in enumerate(as_list(raw, "components"))]
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


def load_answers(path: Path, require_areas: Sequence[str] = AREAS) -> Answers:
    """Parse and validate the answers file.

    Sections are validated when their area is required or marked done; other
    sections may be incomplete and come back empty (None or ()).
    """
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
    # An area missing from an older interview hasn't been started yet.
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

    base = _project_root(path)
    identity = _identity(get(top, "identity", ""), base) if active("identity") else None
    layout: str | None = None
    comps: tuple[Component, ...] = ()
    if active("components"):
        layout = choice(top, "layout", "", _LAYOUTS)
        comps = _components(get(top, "components", ""), layout)
    git = _git(get(top, "git", "")) if active("git") else None
    workflow = (
        _workflow(get(top, "agent_workflow", "")) if active("agent_workflow") else None
    )
    names = {c.name for c in comps} if active("components") else None
    overrides = tuple(
        _override(o, i, names)
        for i, o in enumerate(as_list(top.get("overrides", []), "overrides"))
    )
    talk = top.get("components_talk", False)
    if not isinstance(talk, bool):
        raise fail("components_talk", "must be true or false", "Use true or false")
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
    decisions = tuple(
        _decision(x, i)
        for i, x in enumerate(as_list(top.get("decisions", []), "decisions"))
    )
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
        overrides,
        decisions,
    )


def write_answers(target: Path, text: str) -> Path:
    """Merge the top-level keys of a JSON object into the target's answers file.

    Each key given replaces that key in the file; the others stay as they are.
    The file and its folders are created when missing, and the new file
    replaces the old one in a single step, so a failed write leaves it intact.
    """
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
