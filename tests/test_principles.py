import copy
import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

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
    data["components"] = [
        {
            "name": "tool",
            "path": ".",
            "kind": "cli",
            "stack": "python",
            "traits": traits,
        }
    ]
    data["components_talk"] = False
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
    assert p["override_decision"] == "docs/decisions/0005-override-observability.md"


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
    assert review["risk_paths"][-1] == "infra/**"


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
    assert parsed["docs_map"] == {}
    assert parsed["components"][0]["commands"]["test"] == "uv run pytest"
    assert parsed["project"] == {"name": "Pico Trust", "slug": "pico-trust"}


def test_branching_is_recorded():
    assert build_principles(D, A, "0.1.0")["git"]["branching"] == "trunk"
