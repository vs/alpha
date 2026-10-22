"""Principles file: merge defaults and interview answers into docs/principles.toml."""

from pathlib import PurePosixPath
from typing import Any, cast

from alpha.answers import Answers, AnswersError, Component
from alpha.recipes import load_recipe
from alpha.toml_write import dumps

_UI_KINDS = frozenset({"frontend", "mobile"})
_COMPONENT_FACTS = (
    "has_ui",
    "deployed",
    "network_calls",
    "persisted_data",
    "ml",
    "nontrivial_logic",
)
_PROJECT_ONLY = (
    "multi_component",
    "communicating_components",
    "budgets_set",
    "domain_jargon",
)

_HEADER = """\
# Single source of truth for this project's principles, review thresholds,
# protected paths and component commands. Edit by hand or through alpha skills;
# hooks and reviewers read this file.
"""


def component_facts(c: Component) -> dict[str, bool]:
    t = c.traits
    return {
        "has_ui": c.kind in _UI_KINDS or t.has_ui,
        "deployed": t.deployed,
        "network_calls": t.network_calls,
        "persisted_data": t.persisted_data,
        "ml": t.ml,
        "nontrivial_logic": t.nontrivial_logic,
    }


def compute_facts(a: Answers) -> dict[str, bool]:
    per = [component_facts(c) for c in a.components]
    multi = len(a.components) > 1
    facts = {key: any(f[key] for f in per) for key in _COMPONENT_FACTS}
    facts["multi_component"] = multi
    facts["communicating_components"] = multi and a.components_talk
    facts["budgets_set"] = False  # Plan 2
    facts["domain_jargon"] = a.identity.domain_jargon if a.identity else False
    return facts


def _prefixed(path: str, glob: str) -> str:
    return glob if path == "." else (PurePosixPath(path) / glob).as_posix()


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _applicable(applies: list[str], a: Answers, project: dict[str, bool]) -> list[str]:
    names: list[str] = []
    for c in a.components:
        facts = component_facts(c)
        for cond in applies:
            if cond == "always" or (
                project[cond] if cond in _PROJECT_ONLY else facts.get(cond, False)
            ):
                names.append(c.name)
                break
    return names


def override_decision_paths(a: Answers, first_number: int) -> dict[int, str]:
    return {
        i: f"docs/decisions/{first_number + i:04d}-override-{o.principle}.md"
        for i, o in enumerate(a.overrides)
    }


def build_principles(
    defaults: dict[str, Any], a: Answers, kit_version: str
) -> dict[str, Any]:
    if a.identity is None or a.git is None or a.agent_workflow is None:
        raise AnswersError(
            "Answers are incomplete: identity, git and agent_workflow must be done. "
            "Finish the interview areas, then retry."
        )
    review = dict(defaults["review"])
    review["mode"] = a.agent_workflow.review_mode
    review["max_lines"] = a.agent_workflow.max_lines
    review["max_files"] = a.agent_workflow.max_files
    review["risk_paths"] = _dedupe(
        [*defaults["review"]["risk_paths"], *a.agent_workflow.extra_risk_paths]
    )

    components: list[dict[str, Any]] = []
    protected = list(defaults["protected"]["paths"])
    for c in a.components:
        recipe = load_recipe(c.stack)
        protected += [_prefixed(c.path, lock) for lock in recipe.lockfiles]
        components.append(
            {
                "name": c.name,
                "path": c.path,
                "kind": c.kind,
                "stack": c.stack,
                "manifests": [_prefixed(c.path, m) for m in recipe.manifests],
                "source_globs": [_prefixed(c.path, g) for g in recipe.source_globs],
                "test_globs": [_prefixed(c.path, g) for g in recipe.test_globs],
                "exclude_globs": [_prefixed(c.path, g) for g in recipe.exclude_globs],
                "commands": dict(recipe.commands),
            }
        )

    project = compute_facts(a)
    principles: list[dict[str, Any]] = []
    for p in defaults["principles"]:
        names = _applicable(list(p["applies"]), a, project)
        principles.append(
            {
                "id": p["id"],
                "title": p["title"],
                "statement": p["statement"],
                "rationale": p["rationale"],
                "applies": list(p["applies"]),
                "core": p["core"],
                "checked_by": list(p["checked_by"]),
                "active": bool(names),
                "components": names,
                "override_decision": "",
                "params": dict(p.get("params", {})),
                "component_params": {},  # per component, on top of params
            }
        )

    by_id = {p["id"]: p for p in principles}
    decision_paths = override_decision_paths(a, len(a.decisions) + 1)
    for i, o in enumerate(a.overrides):
        target = by_id.get(o.principle)
        if target is None:
            raise AnswersError(
                f"overrides[{i}].principle: unknown principle '{o.principle}'. "
                f"Known ids: {', '.join(sorted(by_id))}."
            )
        comp = o.scope.removeprefix("component:") if o.scope != "project" else None
        if o.change in ("tighten", "loosen"):
            if comp is None:
                cast(dict[str, Any], target["params"]).update(o.params)
            elif o.params:
                per = cast(dict[str, dict[str, Any]], target["component_params"])
                per.setdefault(comp, {}).update(o.params)
        elif comp is not None:
            target["components"] = [n for n in target["components"] if n != comp]
            if not target["components"]:
                target["active"] = False
        else:
            target["active"] = False
        target["override_decision"] = decision_paths[i]

    return {
        "schema": 1,
        "kit_version": kit_version,
        "project": {"name": a.identity.name, "slug": a.identity.slug},
        "review": review,
        "protected": {"paths": _dedupe(protected)},
        "git": {
            "convention": a.git.convention,
            "types": list(defaults["git"]["types"]),
            "scopes": list(a.git.scopes),
            "branching": a.git.branching,
        },
        "docs_map": {},  # filled by plan 2's documentation area
        "components": components,
        "principles": principles,
    }


def render_principles(data: dict[str, Any]) -> str:
    return _HEADER + "\n" + dumps(data)
