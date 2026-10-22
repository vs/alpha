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
    override_decision_paths,
    render_principles,
)

FIXTURE = Path(__file__).parent / "fixtures" / "answers_valid.json"
D = load_defaults(Source(PLUGIN_ROOT, True, ""))
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
    assert review["risk_paths"][-2:] == ["infra/**", "api/openapi.yaml"]


def test_facts():
    facts = compute_facts(A)
    assert facts["has_ui"] and facts["communicating_components"]
    assert not facts["budgets_set"] and not facts["ml"]


def test_override_decision_paths():
    assert override_decision_paths(A, 5) == {
        0: "docs/decisions/0005-override-observability.md"
    }


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


@pytest.mark.parametrize("area", ["documentation", "build"])
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
        build_principles(D, variant(tmp_path, mutate), "0.1.0")
