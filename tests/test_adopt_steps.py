"""The compliance plan of an adopted repo (spec §5b, step 6)."""

from pathlib import Path
from typing import Any

import pytest
from helpers import adoption_answers

from alpha.answers import AnswersError, load_answers

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
