"""Interview answers (.claude/alpha/project.json): model and validation."""

import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

PROJECT_JSON = ".claude/alpha/project.json"
AREAS: tuple[str, ...] = ("identity", "components", "git", "agent_workflow")
KINDS: frozenset[str] = frozenset(
    {"backend", "frontend", "cli", "mobile", "ml", "library", "worker"}
)
STACKS: frozenset[str] = frozenset({"python", "typescript"})
LICENSES: frozenset[str] = frozenset({"MIT", "Apache-2.0", "Proprietary"})
_STATUSES = ("done", "in_progress", "pending")
_LAYOUTS = ("monorepo", "single")
_CHANGES = ("tighten", "loosen", "drop")
_REVIEW_MODES = ("batched", "every-task")
_NAME = re.compile(r"[a-z][a-z0-9-]*")
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
        "overrides",
        "decisions",
        "manifest",
    }
)


class AnswersError(Exception):
    pass


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
    overrides: tuple[Override, ...]
    decisions: tuple[Decision, ...]


def _fail(where: str, problem: str, fix: str) -> AnswersError:
    return AnswersError(f"{where}: {problem}. {fix}")


def _join(parent: str, key: str) -> str:
    return f"{parent}.{key}" if parent else key


def _obj(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise _fail(where, "must be an object", "Write it as a JSON object { ... }")
    return cast(Mapping[str, Any], value)


def _list(value: object, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise _fail(where, "must be a list", "Write it as a JSON list [ ... ]")
    return cast(list[Any], value)


def _get(d: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise _fail(_join(where, key), "is missing", f'Add the "{key}" field')
    return d[key]


def _str(d: Mapping[str, Any], key: str, where: str, *, blank: bool = False) -> str:
    v = _get(d, key, where)
    if not isinstance(v, str) or (not blank and not v.strip()):
        raise _fail(_join(where, key), "must be a non-empty string", "Provide text")
    return v


def _bool(d: Mapping[str, Any], key: str, where: str) -> bool:
    v = _get(d, key, where)
    if not isinstance(v, bool):
        raise _fail(_join(where, key), "must be true or false", "Use true or false")
    return v


def _pos_int(d: Mapping[str, Any], key: str, where: str) -> int:
    v = _get(d, key, where)
    if not isinstance(v, int) or isinstance(v, bool):
        raise _fail(_join(where, key), "must be a whole number", "Use e.g. 200")
    if v <= 0:
        raise _fail(_join(where, key), f"is {v}", "Use a number greater than 0")
    return v


def _choice(d: Mapping[str, Any], key: str, where: str, options: Sequence[str]) -> str:
    v = _get(d, key, where)
    if v not in options:
        raise _fail(
            _join(where, key),
            f"{v!r} is not allowed",
            f"Use one of: {', '.join(sorted(options))}",
        )
    return v


def _strs(d: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    items = _list(_get(d, key, where), _join(where, key))
    out: list[str] = []
    for i, item in enumerate(items):
        if not isinstance(item, str):
            raise _fail(f"{_join(where, key)}[{i}]", "must be a string", "Use text")
        out.append(item)
    return tuple(out)


def _project_root(answers_path: Path) -> Path:
    """Project root for an answers file at <root>/.claude/alpha/project.json."""
    return answers_path.resolve().parent.parent.parent


def _identity(raw: object, base: Path) -> Identity:
    where = "identity"
    d = _obj(raw, where)
    slug = _str(d, "slug", where)
    if not _NAME.fullmatch(slug):
        raise _fail(
            "identity.slug",
            f"{slug!r} is not a valid slug",
            "Use lowercase letters, digits and hyphens, starting with a letter",
        )
    reqs: list[Requirement] = []
    for i, r in enumerate(
        _list(_get(d, "requirements", where), "identity.requirements")
    ):
        rw = f"identity.requirements[{i}]"
        ro = _obj(r, rw)
        reqs.append(
            Requirement(
                _str(ro, "id", rw), _str(ro, "text", rw), _str(ro, "acceptance", rw)
            )
        )
    license_file = d.get("license_file")
    if license_file is not None and not isinstance(license_file, str):
        raise _fail("identity.license_file", "must be a path or null", "Use a path")
    license_ = _str(d, "license", where)
    if license_file is not None:
        resolved = base / license_file  # an absolute license_file wins
        if not resolved.is_file():
            raise _fail(
                "identity.license_file",
                f"{resolved} does not exist",
                "Point it at an existing file, or set it to null and pick MIT, "
                "Apache-2.0 or Proprietary",
            )
    elif license_ not in LICENSES:
        raise _fail(
            "identity.license",
            f"{license_!r} is not a built-in license",
            "Use MIT, Apache-2.0 or Proprietary, "
            "or set license_file to your own license text",
        )
    return Identity(
        name=_str(d, "name", where),
        slug=slug,
        value_proposition=_str(d, "value_proposition", where),
        target_users=_str(d, "target_users", where),
        requirements=tuple(reqs),
        license=license_,
        license_file=license_file,
        copyright_holder=_str(d, "copyright_holder", where),
        domain_jargon=_bool(d, "domain_jargon", where),
    )


def _component(raw: object, i: int) -> Component:
    where = f"components[{i}]"
    d = _obj(raw, where)
    name = _str(d, "name", where)
    if not _NAME.fullmatch(name):
        raise _fail(
            f"{where}.name",
            f"{name!r} is not a valid name",
            "Use lowercase letters, digits and hyphens, starting with a letter",
        )
    path = _str(d, "path", where)
    parts = PurePosixPath(path).parts
    if path.startswith("/") or ".." in parts:
        raise _fail(
            f"{where}.path",
            f"{path!r} must be relative to the project root",
            'Use a folder like "api", without a leading "/" or ".."',
        )
    stack = _str(d, "stack", where)
    if stack not in STACKS:
        raise _fail(
            f"{where}.stack",
            f"{stack} is not supported yet; alpha 0.1 supports python and typescript",
            "Pick one, or wait for the generic-stack recipe (plan 2)",
        )
    tw = f"{where}.traits"
    t = _obj(_get(d, "traits", where), tw)
    traits = Traits(**{k: _bool(t, k, tw) for k in _TRAITS})
    return Component(
        name, path, _choice(d, "kind", where, sorted(KINDS)), stack, traits
    )


def _components(raw: object, layout: str) -> tuple[Component, ...]:
    comps = [_component(c, i) for i, c in enumerate(_list(raw, "components"))]
    if not comps:
        raise _fail("components", "is empty", "Add at least one component")
    seen: dict[str, int] = {}
    for i, c in enumerate(comps):
        if c.name in seen:
            raise _fail(
                f"components[{i}].name",
                f"duplicate name {c.name!r} (also components[{seen[c.name]}])",
                "Give each component its own name",
            )
        seen[c.name] = i
    if layout == "single":
        if len(comps) != 1:
            raise _fail(
                "layout",
                f"single needs exactly one component, found {len(comps)}",
                'Set layout to "monorepo", or remove components',
            )
        if comps[0].path != ".":
            raise _fail(
                "components[0].path",
                f"is {comps[0].path!r} but layout is single",
                'Set path to "." or change layout to "monorepo"',
            )
    for i, c in enumerate(comps):
        for j, o in enumerate(comps[:i]):
            a, b = PurePosixPath(c.path).parts, PurePosixPath(o.path).parts
            if a[: len(b)] == b or b[: len(a)] == a:
                inner, outer = (i, j) if len(a) >= len(b) else (j, i)
                raise _fail(
                    f"components[{inner}].path",
                    f"{comps[inner].path!r} is inside (or equal to) "
                    f"components[{outer}].path {comps[outer].path!r}",
                    "Give each component its own folder, not nested in another",
                )
    return tuple(comps)


def _git(raw: object) -> GitPrefs:
    d = _obj(raw, "git")
    scopes = _strs(d, "scopes", "git")
    for i, scope in enumerate(scopes):
        if not _SCOPE.fullmatch(scope):
            raise _fail(
                f"git.scopes[{i}]",
                f"{scope!r} can't be a commit scope",
                "Use only lowercase letters, digits and hyphens, e.g. "
                '"api" or "deps"; the commit-msg hook rejects anything else',
            )
    return GitPrefs(_str(d, "convention", "git"), scopes, _str(d, "branching", "git"))


def _workflow(raw: object) -> AgentWorkflow:
    w = "agent_workflow"
    d = _obj(raw, w)
    return AgentWorkflow(
        _choice(d, "review_mode", w, _REVIEW_MODES),
        _pos_int(d, "max_lines", w),
        _pos_int(d, "max_files", w),
        _strs(d, "extra_risk_paths", w),
    )


def _override(raw: object, i: int, names: set[str] | None) -> Override:
    where = f"overrides[{i}]"
    d = _obj(raw, where)
    change = _choice(d, "change", where, _CHANGES)
    scope = _str(d, "scope", where)
    if scope != "project":
        name = (
            scope.removeprefix("component:") if scope.startswith("component:") else None
        )
        if name is None:
            raise _fail(
                f"{where}.scope",
                f"{scope!r} is not a valid scope",
                'Use "project" or "component:<name>"',
            )
        if names is not None and name not in names:
            raise _fail(
                f"{where}.scope",
                f"there is no component named {name!r}",
                f"Use one of: {', '.join(sorted(names)) or '(none)'}",
            )
    reason = d.get("reason", "")
    if not isinstance(reason, str):
        raise _fail(f"{where}.reason", "must be text", "Write the reason as a string")
    if change in ("loosen", "drop") and not reason.strip():
        raise _fail(
            f"{where}.reason",
            f"a reason is required when you {change} a principle",
            "Explain why this project is an exception",
        )
    params = d.get("params", {})
    return Override(
        _str(d, "principle", where),
        scope,
        change,
        dict(_obj(params, f"{where}.params")),
        reason,
    )


def _decision(raw: object, i: int) -> Decision:
    where = f"decisions[{i}]"
    d = _obj(raw, where)
    return Decision(
        _choice(d, "area", where, AREAS),
        _str(d, "title", where),
        _str(d, "context", where),
        _str(d, "decision", where),
        _str(d, "consequences", where),
    )


def load_answers(path: Path, require_areas: Sequence[str] = AREAS) -> Answers:
    """Parse and validate the answers file.

    Sections are validated when their area is required or marked done; other
    sections may be incomplete and come back empty (None or ()).
    """
    try:
        text = path.read_text()
    except OSError:
        raise _fail(
            str(path),
            "file not found or unreadable",
            "Run the alpha interview first, or pass the right path",
        ) from None
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as e:
        raise _fail(
            str(path), f"not valid JSON ({e.msg} at line {e.lineno})", "Fix the syntax"
        ) from None
    top = _obj(data, str(path))
    for key in top:
        if key not in _TOP_KEYS:
            raise _fail(
                key,
                "unknown key",
                f"Remove it; allowed keys are {', '.join(sorted(_TOP_KEYS))}",
            )
    for area in require_areas:
        if area not in AREAS:
            raise _fail(
                "area", f"{area!r} is not an area", f"Use one of: {', '.join(AREAS)}"
            )
    schema = _get(top, "schema", "")
    if schema != 1:
        raise _fail("schema", f"{schema!r} is not supported", "Set schema to 1")
    areas_raw = _obj(_get(top, "areas", ""), "areas")
    areas: dict[str, str] = {
        a: _choice(areas_raw, a, "areas", _STATUSES) for a in AREAS
    }
    for area in require_areas:
        if areas[area] != "done":
            raise _fail(
                f"areas.{area}",
                f"is {areas[area]}, not done",
                f"Finish the {area} part of the interview, then retry",
            )

    def active(area: str) -> bool:
        return area in require_areas or areas[area] == "done"

    base = _project_root(path)
    identity = (
        _identity(_get(top, "identity", ""), base) if active("identity") else None
    )
    layout: str | None = None
    comps: tuple[Component, ...] = ()
    if active("components"):
        layout = _choice(top, "layout", "", _LAYOUTS)
        comps = _components(_get(top, "components", ""), layout)
    git = _git(_get(top, "git", "")) if active("git") else None
    workflow = (
        _workflow(_get(top, "agent_workflow", "")) if active("agent_workflow") else None
    )
    names = {c.name for c in comps} if active("components") else None
    overrides = tuple(
        _override(o, i, names)
        for i, o in enumerate(_list(top.get("overrides", []), "overrides"))
    )
    decisions = tuple(
        _decision(x, i)
        for i, x in enumerate(_list(top.get("decisions", []), "decisions"))
    )
    have = {d.area for d in decisions}
    for area in AREAS:
        if areas[area] == "done" and area not in have:
            raise _fail(
                "decisions",
                f"no decision recorded for the done area {area!r}",
                f'Add a decision with "area": "{area}" '
                "(title, context, decision, consequences)",
            )
    talk = top.get("components_talk", False)
    if not isinstance(talk, bool):
        raise _fail("components_talk", "must be true or false", "Use true or false")
    return Answers(
        1, areas, identity, layout, talk, comps, git, workflow, overrides, decisions
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
        raise _fail(
            "input",
            f"not valid JSON ({e.msg} at line {e.lineno})",
            "Fix the syntax: pass one object on one line in single quotes, "
            "writing each ' inside it as '\\''",
        ) from None
    if not isinstance(update, dict):
        raise _fail(
            "input",
            f"expected a JSON object, got {type(update).__name__}",
            'Send the keys to save as one object, e.g. {"layout": "single"}',
        )
    for key in cast(dict[str, Any], update):
        if key == "manifest":
            raise _fail(
                key,
                "is written by alpha generate, not by the interview",
                "Leave it out",
            )
        if key not in _TOP_KEYS:
            raise _fail(
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
        except (OSError, json.JSONDecodeError) as e:
            raise _fail(
                str(path),
                f"can't merge into it, it's not valid JSON ({e})",
                "Fix the file by hand, or delete it to start the interview over",
            ) from None
        if not isinstance(current, dict):
            raise _fail(
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
        raise _fail(
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
