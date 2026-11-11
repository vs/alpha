"""The compliance plan of an adopted repo (spec §5b, step 6)."""

import json
from pathlib import Path
from typing import Any

import pytest
from helpers import PLUGIN_ROOT, adoption_answers, proven, run_cli

from alpha.adopt import gaps, merge_steps
from alpha.answers import AnswersError, load_answers
from alpha.defaults import Source, load_defaults

PROJECT = ".claude/alpha/project.json"


def step(sid: str = "p2-lint-ml", **fields: Any) -> dict[str, Any]:
    return {
        "id": sid,
        "phase": "P2",
        "title": "Add a linter for ml",
        "why": "Nothing checks ml's code style.",
        "component": "ml",
        "principles": ["no-dead-code"],
        "acceptance": [
            {"recipe": "ml.commands.lint"},
            {"run": "mise run check:component:ml"},
        ],
        "status": "pending",
        **fields,
    }


def answers_with(tmp_path: Path, steps: list[dict[str, Any]]) -> Any:
    (tmp_path / "LICENSE").write_text("Ours.\n")
    adoption_answers(tmp_path, steps=steps)
    return load_answers(tmp_path / PROJECT)


def test_steps_load(tmp_path: Path):
    steps = [
        step("p1-format-ml", phase="P1"),
        step(depends_on=["p1-format-ml"], branch="alpha/p2-lint-ml"),
        step(
            "p4-errors",
            phase="P4",
            component=None,
            acceptance=[{"confirm": "Every API error says how to fix it"}],
            status="dropped",
            decision=12,
        ),
    ]
    del steps[2]["component"]
    a = answers_with(tmp_path, steps)
    assert [s.id for s in a.steps] == ["p1-format-ml", "p2-lint-ml", "p4-errors"]
    assert a.steps[1].depends_on == ("p1-format-ml",)
    assert a.steps[1].acceptance[1].kind == "run"
    assert a.steps[2].decision == 12 and a.steps[2].component is None


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        ([step("P2_Lint")], r"steps\[0\]\.id: 'P2_Lint' isn't a lowercase id"),
        ([step(), step()], r"steps\[1\]\.id: p2-lint-ml is used twice"),
        ([step(phase="P9")], r"steps\[0\]\.phase"),
        ([step(status="later")], r"steps\[0\]\.status"),
        ([step(depends_on=["p9-later"])], r"isn't a step listed before this one"),
        ([step(acceptance=[])], r"steps\[0\]\.acceptance: is empty"),
        (
            [step(acceptance=[{"vibes": "ok"}])],
            r"acceptance\[0\]: must name exactly one",
        ),
        (
            [step(acceptance=[{"recipe": "ghost.coverage"}])],
            r"no component named 'ghost'",
        ),
        (
            [step(acceptance=[{"recipe": "ml.commands.deploy"}])],
            r"isn't a recipe field",
        ),
        (
            [step(acceptance=[{"no_baseline": "x", "dir": "a"}])],
            r"dir: only goes with run",
        ),
        ([step(status="dropped")], r"decision: is missing for a dropped step"),
        ([step(component="ghost")], r"steps\[0\]\.component: no component named"),
        ([step(owner="me")], r"steps\[0\]\.owner: unknown key"),
    ],
)
def test_bad_steps_are_named(tmp_path: Path, steps: list[dict[str, Any]], message: str):
    with pytest.raises(AnswersError, match=message):
        answers_with(tmp_path, steps)


# --- alpha adopt gaps ---

DEFAULTS = load_defaults(Source(PLUGIN_ROOT, True))


def gap_answers(tmp_path: Path, **adoption: Any) -> Any:
    (tmp_path / "LICENSE").write_text("Ours.\n")
    data = adoption_answers(tmp_path, **adoption)
    return data


def _load(tmp_path: Path, data: dict[str, Any]) -> Any:
    (tmp_path / PROJECT).write_text(json.dumps(data))
    return load_answers(tmp_path / PROJECT)


def test_gaps_from_baselines_and_recipe(tmp_path: Path):
    data = gap_answers(tmp_path, baselines=["typecheck:ml", "typos"])
    recipe = {
        "adopted": True,
        "extends": "python",
        "commands": {"format_check": "", "lint": "", "lint_file": ""},
    }
    data["recipes"] = {"ml-python": proven(recipe)}
    found = gaps(_load(tmp_path, data), DEFAULTS)
    assert [s["id"] for s in found] == [
        "p1-format-ml",
        "p2-lint-ml",
        "p2-coverage-ml",
        "p5-baseline-typecheck-ml",
        "p5-baseline-typos",
    ]
    by_id = {s["id"]: s for s in found}
    assert by_id["p5-baseline-typecheck-ml"]["depends_on"] == ["p1-format-ml"]
    assert by_id["p5-baseline-typecheck-ml"]["principles"] == ["strict-types"]
    assert by_id["p5-baseline-typos"]["principles"] == ["docs-with-code"]
    assert by_id["p2-lint-ml"]["acceptance"] == [
        {"recipe": "ml.commands.lint"},
        {"run": "mise run check:component:ml"},
    ]
    # They're valid steps as they stand.
    data["adoption"]["steps"] = found
    assert [s.id for s in _load(tmp_path, data).steps] == list(by_id)


def test_chain_gap(tmp_path: Path):
    data = gap_answers(tmp_path, git_hooks="chain")
    found = gaps(_load(tmp_path, data), DEFAULTS)
    assert found[0]["id"] == "p0-chain-commit-hook"
    assert found[0]["acceptance"] == [{"commit_hook": True}]


def test_no_gaps_for_a_compliant_project(tmp_path: Path):
    data = gap_answers(tmp_path)
    recipe = {
        "adopted": True,
        "extends": "python",
        "coverage": "uv run pytest --cov",
        "coverage_report": "coverage.xml",
    }
    data["recipes"] = {"ml-python": proven(recipe)}
    assert gaps(_load(tmp_path, data), DEFAULTS) == []


def test_gaps_save_adds_only_new_steps(tmp_path: Path):
    old = step("p2-coverage-ml", status="in_progress", title="Our own words")
    found = [step("p2-coverage-ml"), step("p5-baseline-typos", phase="P5")]
    merged = merge_steps([old], found)
    assert merged == [old, found[1]]


def test_gaps_cli_prints_and_saves(tmp_path: Path):
    gap_answers(tmp_path, baselines=["typos"])
    done = run_cli("adopt", "gaps", str(tmp_path), "--save")
    assert done.returncode == 0, done.stderr
    assert "Added 2 steps to adoption.steps." in done.stdout  # coverage, typos
    saved = json.loads((tmp_path / PROJECT).read_text())["adoption"]
    assert saved["baselines"] == ["typos"] and len(saved["steps"]) == 2
    again = run_cli("adopt", "gaps", str(tmp_path), "--save")
    assert "Added 0 steps" in again.stdout
