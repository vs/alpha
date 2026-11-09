"""Principles file: merge defaults and interview answers into docs/principles.toml."""

from typing import Any, cast

from alpha.answers import AREAS, Answers, AnswersError, Component, Documentation
from alpha.records import Records, record_paths
from alpha.registry import Registry, default_registry
from alpha.repo_checks import principles_entries, repo_checks
from alpha.toml_write import dumps
from alpha.validate import prefixed

_COMPONENT_FACTS = (
    "has_ui",
    "deployed",
    "network_calls",
    "persisted_data",
    "ml",
    "nontrivial_logic",
    "budgets_set",
)
_PROJECT_ONLY = (
    "multi_component",
    "communicating_components",
    "domain_jargon",
)

_HEADER = """\
# Single source of truth for this project's principles, review thresholds,
# protected paths and component commands. Edit by hand or through alpha skills;
# hooks and reviewers read this file.
"""


def _budgets(a: Answers) -> dict[str, list[str]]:
    """Each component's budgets, as "<metric>: <limit> (<measured by>)"; the
    limit is the user's text, so it keeps its own direction (e.g. "at least 90")."""
    plans = a.performance.components if a.performance else ()
    return {
        p.name: [f"{b.metric}: {b.limit} ({b.measured_by})" for b in p.budgets]
        for p in plans
        if p.budgets
    }


def component_facts(c: Component, a: Answers) -> dict[str, bool]:
    t = c.traits
    return {
        "has_ui": c.has_ui,
        "deployed": t.deployed,
        "network_calls": t.network_calls,
        "persisted_data": t.persisted_data,
        "ml": t.ml,
        "nontrivial_logic": t.nontrivial_logic,
        "budgets_set": c.name in _budgets(a),
    }


def compute_facts(a: Answers) -> dict[str, bool]:
    per = [component_facts(c, a) for c in a.components]
    multi = len(a.components) > 1
    facts = {key: any(f[key] for f in per) for key in _COMPONENT_FACTS}
    facts["multi_component"] = multi
    facts["communicating_components"] = multi and a.components_talk
    facts["domain_jargon"] = a.identity.domain_jargon if a.identity else False
    return facts


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _applicable(applies: list[str], a: Answers, project: dict[str, bool]) -> list[str]:
    names: list[str] = []
    for c in a.components:
        facts = component_facts(c, a)
        for cond in applies:
            if cond == "always" or (
                project[cond] if cond in _PROJECT_ONLY else facts.get(cond, False)
            ):
                names.append(c.name)
                break
    return names


def _docs_map(documentation: Documentation) -> dict[str, list[str]]:
    """Each mapped glob to the docs that must change with it."""
    out: dict[str, list[str]] = {}
    for m in documentation.mappings:
        for glob in m.paths:
            out[glob] = _dedupe([*out.get(glob, []), *m.docs])
    return out


def build_principles(
    defaults: dict[str, Any],
    a: Answers,
    kit_version: str,
    records: Records | None = None,
    *,
    registry: Registry | None = None,
) -> dict[str, Any]:
    missing = [area for area in AREAS if area != "components" and not getattr(a, area)]
    if missing:
        raise AnswersError(
            f"Answers are incomplete: {', '.join(missing)} must be done. Finish "
            "the interview areas, then retry."
        )
    assert a.git and a.agent_workflow and a.documentation and a.identity
    assert a.security and a.architecture and a.ui and a.data and a.accessibility
    migration_paths = _dedupe([g for d in a.data.components for g in d.migrations])
    squawk_paths = _dedupe(
        [
            g
            for d in a.data.components
            if "postgres" in d.storage.lower()
            for g in d.migrations
        ]
    )
    tokens = {u.name: u.tokens for u in a.ui.components}
    review = dict(defaults["review"])
    review["mode"] = a.agent_workflow.review_mode
    review["max_lines"] = a.agent_workflow.max_lines
    review["max_files"] = a.agent_workflow.max_files
    review["risk_paths"] = _dedupe(
        [
            *defaults["review"]["risk_paths"],
            *a.agent_workflow.extra_risk_paths,
            *a.architecture.contracts.paths,
            *migration_paths,
            *(p for t in tokens.values() for p in (t, f"{t}/**")),
        ]
    )

    components: list[dict[str, Any]] = []
    protected = list(defaults["protected"]["paths"])
    book = a.book()
    for c in a.components:
        recipe = book.get(c.stack)
        protected += [prefixed(c.path, lock) for lock in recipe.lockfiles]
        components.append(
            {
                "name": c.name,
                "path": c.path,
                "kind": c.kind,
                "stack": c.stack,
                "manifests": [prefixed(c.path, m) for m in recipe.manifests],
                "lockfiles": [prefixed(c.path, lock) for lock in recipe.lockfiles],
                "source_globs": [prefixed(c.path, g) for g in recipe.source_globs],
                "test_globs": [prefixed(c.path, g) for g in recipe.test_globs],
                "exclude_globs": [prefixed(c.path, g) for g in recipe.exclude_globs],
                "commands": dict(recipe.commands),
                "rules": [
                    {"id": f"{c.stack}:{r.id}", "rule": r.rule} for r in recipe.rules
                ],
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
    # What the interview set, before overrides change it.
    if a.accessibility.level:
        by_id["accessibility"]["params"]["level"] = a.accessibility.level
    by_id["perf-budgets"]["component_params"].update(
        {name: {"budgets": b} for name, b in _budgets(a).items()}
    )
    by_id["visual-system"]["component_params"].update(
        {name: {"tokens": t} for name, t in tokens.items()}
    )
    by_id["accessibility"]["component_params"].update(
        {c.name: {"checks": c.checks} for c in a.accessibility.components}
    )
    if a.data.ml is not None:
        ml = {
            "data_versioning": a.data.ml.versioning,
            "seeds": a.data.ml.seeds,
            "tracking": a.data.ml.tracking,
        }
        by_id["reproducible"]["component_params"].update(
            {c.name: dict(ml) for c in a.components if c.traits.ml}
        )
    override_paths = (records or record_paths(a)).overrides
    present = {c.name for c in a.components}
    for i, o in enumerate(a.overrides):
        target = by_id.get(o.principle)
        if target is None:
            raise AnswersError(
                f"overrides[{i}].principle: unknown principle '{o.principle}'. "
                f"Known ids: {', '.join(sorted(by_id))}."
            )
        comp = o.scope.removeprefix("component:") if o.scope != "project" else None
        if comp is not None and comp not in present:
            continue  # its component was removed or renamed: it no longer applies
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
        target["override_decision"] = override_paths[i]

    docs_map = _docs_map(a.documentation)
    protected += a.security.extra_protected
    out: dict[str, Any] = {
        "schema": 1,
        "kit_version": kit_version,
        "project": {"name": a.identity.name, "slug": a.identity.slug},
        "review": review,
        # extra: the project's own additions, as opposed to secrets and lockfiles
        "protected": {
            "paths": _dedupe(protected),
            "extra": list(a.security.extra_protected),
        },
        "git": {
            "convention": a.git.convention,
            "types": list(defaults["git"]["types"]),
            "scopes": list(a.git.scopes),
            "branching": a.git.branching,
        },
        "docs_map": docs_map,
        "data": {"migration_paths": migration_paths, "squawk_paths": squawk_paths},
        "components": components,
        "principles": principles,
    }
    pins = registry or default_registry()
    out["repo_checks"] = principles_entries(repo_checks(a, out, pins))
    return out


def render_principles(data: dict[str, Any]) -> str:
    return _HEADER + "\n" + dumps(data)
