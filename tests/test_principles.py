import copy
import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
from helpers import override_record, single_component

from alpha.answers import Answers, AnswersError, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import (
    build_principles,
    compute_facts,
    render_principles,
)
from alpha.records import Records

FIXTURE = Path(__file__).parent / "fixtures" / "answers_valid.json"
D = load_defaults(Source(PLUGIN_ROOT, True))
A = load_answers(FIXTURE)


def variant(tmp_path: Path, mutate: Any) -> Answers:
    data = copy.deepcopy(json.loads(FIXTURE.read_text()))
    mutate(data)
    path = tmp_path / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data))
    return load_answers(path)


def principle(out: dict[str, Any], pid: str) -> dict[str, Any]:
    return next(p for p in out["principles"] if p["id"] == pid)


def cli_only(data: dict[str, Any]) -> None:
    traits = dict.fromkeys(
        [
            "has_ui",
            "deployed",
            "network_calls",
            "persisted_data",
            "ml",
            "nontrivial_logic",
        ],
        False,
    )
    tool = {"name": "tool", "path": ".", "kind": "cli", "stack": "python"}
    single_component(data, {**tool, "traits": traits})
    data["git"]["scopes"] = ["tool"]
    data["overrides"] = []


def test_cli_only_project_has_no_visual_system(tmp_path: Path):
    out = build_principles(D, variant(tmp_path, cli_only), "0.1.0")
    assert principle(out, "visual-system")["active"] is False
    assert principle(out, "contracts")["active"] is False
    assert out["components"][0]["source_globs"] == ["**/*.py"]
    assert "**/.*/**" in out["components"][0]["exclude_globs"]
    assert "uv.lock" in out["protected"]["paths"]


def test_two_talking_components_enable_contracts():
    p = principle(build_principles(D, A, "0.1.0"), "contracts")
    assert p["active"] is True
    assert p["components"] == ["api", "web"]


def test_component_scoped_condition(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["components"][1]["traits"]["network_calls"] = False
        data["overrides"] = []

    out = build_principles(D, variant(tmp_path, mutate), "0.1.0")
    assert principle(out, "timeouts")["components"] == ["api"]


def test_drop_for_one_component(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["overrides"][0]["change"] = "drop"

    a = variant(tmp_path, mutate)
    p = principle(build_principles(D, a, "0.1.0"), "observability")
    assert p["components"] == ["web"]
    assert p["active"] is True
    data = json.loads(FIXTURE.read_text())
    assert p["override_decision"] == override_record(data, "observability")


def test_drop_last_component_or_project_deactivates(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["overrides"] = [
            {
                "principle": "safe-migrations",
                "scope": "component:api",
                "change": "drop",
                "params": {},
                "reason": "x",
            },
            {
                "principle": "accessibility",
                "scope": "project",
                "change": "drop",
                "params": {},
                "reason": "x",
            },
        ]

    out = build_principles(D, variant(tmp_path, mutate), "0.1.0")
    assert principle(out, "safe-migrations")["active"] is False
    assert principle(out, "accessibility")["active"] is False


def test_tighten_merges_params(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["overrides"] = [
            {
                "principle": "timeouts",
                "scope": "project",
                "change": "tighten",
                "params": {"seconds": 5},
                "reason": "x",
            }
        ]

    p = principle(build_principles(D, variant(tmp_path, mutate), "0.1.0"), "timeouts")
    assert p["params"] == {"seconds": 5}
    assert p["active"] is True


def test_component_tighten_keeps_project_params(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["overrides"] = [
            {
                "principle": "timeouts",
                "scope": "component:api",
                "change": "tighten",
                "params": {"seconds": 5},
                "reason": "",
            },
            {
                "principle": "timeouts",
                "scope": "component:web",
                "change": "loosen",
                "params": {"seconds": 30},
                "reason": "x",
            },
        ]

    out = build_principles(D, variant(tmp_path, mutate), "0.1.0")
    p = principle(out, "timeouts")
    assert p["params"] == {}
    assert p["component_params"] == {"api": {"seconds": 5}, "web": {"seconds": 30}}
    assert p["components"] == ["api", "web"]
    reread = principle(tomllib.loads(render_principles(out)), "timeouts")
    assert reread["component_params"] == p["component_params"]


def test_project_tighten_leaves_component_params_empty(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["overrides"] = [
            {
                "principle": "timeouts",
                "scope": "project",
                "change": "tighten",
                "params": {"seconds": 5},
                "reason": "x",
            }
        ]

    p = principle(build_principles(D, variant(tmp_path, mutate), "0.1.0"), "timeouts")
    assert p["component_params"] == {}


def test_component_tighten_without_params_adds_no_table():
    p = principle(build_principles(D, A, "0.1.0"), "observability")
    assert p["component_params"] == {}


def test_unknown_override_principle(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["overrides"][0]["principle"] = "nope"

    with pytest.raises(
        AnswersError,
        match=r"overrides\[0\]\.principle: unknown principle 'nope'. Known ids: ",
    ):
        build_principles(D, variant(tmp_path, mutate), "0.1.0")


def test_lockfiles_become_protected():
    paths = build_principles(D, A, "0.1.0")["protected"]["paths"]
    assert "api/uv.lock" in paths
    assert "web/pnpm-lock.yaml" in paths
    assert "**/.env" in paths


def test_review_settings_come_from_answers(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["agent_workflow"].update(
            review_mode="every-task",
            max_lines=50,
            extra_risk_paths=["infra/**", "docs/principles.toml"],
        )

    review = build_principles(D, variant(tmp_path, mutate), "0.1.0")["review"]
    assert review["max_lines"] == 50
    assert review["mode"] == "every-task"
    assert review["risk_paths"].count("docs/principles.toml") == 1
    assert review["risk_paths"][-5:] == [
        "infra/**",
        "api/openapi.yaml",
        "api/migrations/versions/**",
        "web/src/styles/tokens.css",
        "web/src/styles/tokens.css/**",
    ]


def test_facts():
    facts = compute_facts(A)
    assert facts["has_ui"] and facts["communicating_components"]
    assert facts["budgets_set"] and not facts["ml"]


def test_override_decision_comes_from_the_records():
    records = Records((), ("docs/decisions/0042-override-observability.md",))
    p = build_principles(D, A, "0.1.0", records)
    by_id = {x["id"]: x for x in p["principles"]}
    assert by_id["observability"]["override_decision"] == records.overrides[0]


def test_output_parses_and_is_deterministic():
    s1 = render_principles(build_principles(D, A, "0.1.0"))
    s2 = render_principles(build_principles(D, A, "0.1.0"))
    parsed = tomllib.loads(s1)
    assert s1 == s2 and parsed["schema"] == 1
    assert parsed["docs_map"] == {
        "api/**/routes/**": ["docs/guide/**"],
        "web/**/pages/**": ["docs/guide/**"],
        "**/openapi*.yaml": ["docs/architecture.md"],
    }
    assert parsed["components"][0]["commands"]["test"] == "uv run pytest"
    assert parsed["project"] == {"name": "Pico Trust", "slug": "pico-trust"}


def test_branching_is_recorded():
    assert build_principles(D, A, "0.1.0")["git"]["branching"] == "trunk"


def test_same_glob_in_two_mappings_merges_docs(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["documentation"]["mappings"] = [
            {"paths": ["api/**", "web/**"], "docs": ["docs/a.md", "docs/b.md"]},
            {"paths": ["api/**"], "docs": ["docs/b.md", "docs/c.md"]},
        ]

    out = build_principles(D, variant(tmp_path, mutate), "0.1.0")
    assert out["docs_map"] == {
        "api/**": ["docs/a.md", "docs/b.md", "docs/c.md"],
        "web/**": ["docs/a.md", "docs/b.md"],
    }


@pytest.mark.parametrize(
    "area",
    [
        "documentation",
        "build",
        "ui",
        "releases",
        "data",
        "accessibility",
        "performance",
    ],
)
def test_principles_need_documentation_and_build(tmp_path: Path, area: str):
    data = json.loads(FIXTURE.read_text())
    data["areas"][area] = "pending"
    path = tmp_path / "project.json"
    path.write_text(json.dumps(data))
    a = load_answers(path, ["identity"])
    with pytest.raises(AnswersError, match=area):
        build_principles(D, a, "0.1.0")


def test_extra_protected_and_contract_paths_reach_the_principles():
    out = build_principles(D, A, "0.1.0")
    assert "api/keys/**" in out["protected"]["paths"]
    assert "api/openapi.yaml" in out["review"]["risk_paths"]


@pytest.mark.parametrize(
    ("glob", "blocked"),
    [
        ("docs/**", "docs/principles.toml"),
        ("**/*.toml", "docs/principles.toml"),
        ("**/package.json", "web/package.json"),
        ("docs/guide/**", "docs/guide/**"),
        ("docs/dependencies.md", "docs/dependencies.md"),
        ("**/tests/**", "api/tests/**/*.py (tests)"),
        ("web/**/*.test.ts", "web/**/*.test.ts (tests)"),
    ],
)
def test_protecting_what_checks_must_change_is_refused(
    tmp_path: Path, glob: str, blocked: str
):
    def mutate(data: dict[str, Any]) -> None:
        data["security"]["extra_protected"] = ["api/keys/**", glob]

    with pytest.raises(
        AnswersError,
        match=rf"security\.extra_protected\[1\]: .*{re.escape(blocked)}",
    ):
        variant(tmp_path, mutate)


def scenario_answers(tmp_path: Path, name: str, mutate: Any = None) -> Answers:
    from helpers import SCENARIOS

    data = json.loads((SCENARIOS / f"{name}.json").read_text())
    if mutate:
        mutate(data)
    path = tmp_path / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data))
    return load_answers(path)


def test_perf_budgets_apply_where_budgets_are_set(tmp_path: Path):
    p = principle(build_principles(D, A, "0.1.0"), "perf-budgets")
    assert p["active"] and p["components"] == ["api", "web"]

    def no_web_budgets(data: dict[str, Any]) -> None:
        data["performance"]["components"][1]["budgets"] = []

    out = build_principles(D, variant(tmp_path, no_web_budgets), "0.1.0")
    assert principle(out, "perf-budgets")["components"] == ["api"]
    assert compute_facts(variant(tmp_path / "b", no_web_budgets))["budgets_set"]


def test_no_budgets_turn_perf_budgets_off(tmp_path: Path):
    a = scenario_answers(tmp_path, "python-ml-single")
    assert not compute_facts(a)["budgets_set"]
    p = principle(build_principles(D, a, "0.1.0"), "perf-budgets")
    assert p["active"] is False and p["components"] == []


def test_budgets_reach_the_principle_per_component():
    p = principle(build_principles(D, A, "0.1.0"), "perf-budgets")
    assert p["component_params"] == {
        "api": {"budgets": ["p95 response time: 300 ms (k6 in CI against staging)"]},
        "web": {
            "budgets": [
                "JavaScript bundle: 200 KB gzipped (the build's size report in CI)"
            ]
        },
    }


def test_accessibility_level_and_tokens_reach_the_principles():
    out = build_principles(D, A, "0.1.0")
    assert principle(out, "accessibility")["params"]["level"] == "WCAG 2.2 AA"
    assert principle(out, "visual-system")["component_params"] == {
        "web": {"tokens": "web/src/styles/tokens.css"}
    }


def test_no_ui_sets_no_accessibility_level(tmp_path: Path):
    out = build_principles(D, scenario_answers(tmp_path, "rust-cli"), "0.1.0")
    assert "level" not in principle(out, "accessibility")["params"]
    assert principle(out, "visual-system")["component_params"] == {}


def test_migrations_and_tokens_are_risk_paths(tmp_path: Path):
    out = build_principles(D, A, "0.1.0")
    assert out["data"] == {
        "migration_paths": ["api/migrations/versions/**"],
        # PostgreSQL, but Alembic writes Python migrations squawk can't read.
        "squawk_paths": [],
    }
    risk = out["review"]["risk_paths"]
    assert "api/migrations/versions/**" in risk
    assert "web/src/styles/tokens.css" in risk
    assert "web/src/styles/tokens.css/**" in risk
    assert len(risk) == len(set(risk))


def test_no_stored_data_means_no_migration_paths(tmp_path: Path):
    out = build_principles(D, scenario_answers(tmp_path, "rust-cli"), "0.1.0")
    assert out["data"] == {"migration_paths": [], "squawk_paths": []}


def test_project_override_of_level_wins(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["overrides"].append(
            {
                "principle": "accessibility",
                "scope": "project",
                "change": "tighten",
                "params": {"level": "WCAG 2.2 AAA"},
                "reason": "A public-sector client requires AAA.",
            }
        )

    out = build_principles(D, variant(tmp_path, mutate), "0.1.0")
    assert principle(out, "accessibility")["params"]["level"] == "WCAG 2.2 AAA"


def test_ml_answers_reach_the_reproducible_principle(tmp_path: Path):
    a = scenario_answers(tmp_path, "python-ml-single")
    assert a.data and a.data.ml
    name = a.components[0].name
    p = principle(build_principles(D, a, "0.1.0"), "reproducible")
    assert p["component_params"] == {
        name: {
            "data_versioning": a.data.ml.versioning,
            "seeds": a.data.ml.seeds,
            "tracking": a.data.ml.tracking,
        }
    }


def test_accessibility_checks_reach_the_principle():
    p = principle(build_principles(D, A, "0.1.0"), "accessibility")
    assert p["params"]["level"] == "WCAG 2.2 AA"
    assert p["component_params"] == {
        "web": {"checks": "axe in the end-to-end tests, plus keyboard-only runs of R2"}
    }


def test_components_carry_their_stacks_rules_with_prefixed_ids():
    comps = {c["name"]: c for c in build_principles(D, A, "0.1.0")["components"]}
    assert comps["api"]["rules"][1] == {
        "id": "python:typed-boundaries",
        "rule": "Parse external input (JSON, files, environment, requests) into "
        "dataclasses or typed models at the boundary; don't pass "
        "`dict[str, Any]` inward.",
    }
    assert [r["id"] for r in comps["web"]["rules"]] == [
        "typescript:top-level-imports",
        "typescript:unknown-at-boundaries",
        "typescript:pnpm-for-dependencies",
    ]
    out = tomllib.loads(render_principles(build_principles(D, A, "0.1.0")))
    assert out["components"][0]["rules"] == comps["api"]["rules"]


def _defaults_with(**testing: Any) -> dict[str, Any]:
    d = copy.deepcopy(D)
    d.pop("testing", None)
    if testing:
        d["testing"] = testing
    return d


def test_diff_coverage_answer_overrides_the_default(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["testing"]["diff_coverage"] = 55

    out = build_principles(D, variant(tmp_path, mutate), "0.1.0")
    assert out["testing"] == {"diff_coverage": 55}


def test_diff_coverage_zero_answer_beats_the_default(tmp_path: Path):
    def mutate(data: dict[str, Any]) -> None:
        data["testing"]["diff_coverage"] = 0

    out = build_principles(D, variant(tmp_path, mutate), "0.1.0")
    assert out["testing"] == {"diff_coverage": 0}


def test_diff_coverage_defaults_when_not_answered():
    assert A.testing is not None and A.testing.diff_coverage is None
    out = build_principles(D, A, "0.1.0")
    assert out["testing"] == {"diff_coverage": D["testing"]["diff_coverage"]}


def test_diff_coverage_missing_from_defaults_says_how_to_fix():
    with pytest.raises(AnswersError) as e:
        build_principles(_defaults_with(), A, "0.1.0")
    assert "[testing] diff_coverage is missing" in str(e.value)
    assert "diff_coverage = 80" in str(e.value)


@pytest.mark.parametrize("value", [80.5, "80", True, 101, -1])
def test_diff_coverage_bad_default_says_how_to_fix(value: object):
    with pytest.raises(AnswersError) as e:
        build_principles(_defaults_with(diff_coverage=value), A, "0.1.0")
    assert f"diff_coverage is {value!r}" in str(e.value)
    assert "0 to 100" in str(e.value)


def test_ci_checks_reach_the_built_principles():
    by_id = {p["id"]: p for p in build_principles(D, A, "0.1.0")["principles"]}
    assert "ci:secrets" in by_id["no-secrets"]["checked_by"]
    assert "ci:tree" in by_id["generated-from-source"]["checked_by"]
    assert "ci:migrations" in by_id["safe-migrations"]["checked_by"]
    assert "ci:" not in "".join(by_id["dependency-reasons"]["checked_by"])
