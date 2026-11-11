"""The compliance plan of an adopted repo (spec §5b, step 6)."""

import json
import subprocess
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from helpers import PLUGIN_ROOT, adoption_answers, existing_repo, git, proven, run_cli

from alpha.adopt import (
    AdoptError,
    apply_adoption,
    done,
    drop,
    gaps,
    merge_steps,
    next_step,
    plan_adoption,
)
from alpha.answers import AnswersError, load_answers
from alpha.defaults import Source, load_defaults
from alpha.generate import load_project_principles, render_project
from alpha.gitops import PROPOSALS, commit_update
from alpha.registry import default_registry
from alpha.update import apply_update, plan_update

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


# --- next, start, done, drop ---


def plan_repo(tmp_path: Path, steps: list[dict[str, Any]], **adoption: Any) -> Path:
    root = existing_repo(tmp_path / "repo")
    adoption_answers(root, steps=steps, **adoption)
    return root


def statuses(root: Path) -> dict[str, str]:
    saved = json.loads((root / PROJECT).read_text())["adoption"]["steps"]
    return {s["id"]: s["status"] for s in saved}


def ok(sid: str, phase: str = "P2", **fields: Any) -> dict[str, Any]:
    return step(sid, phase=phase, acceptance=[{"run": "true"}], **fields)


def test_next_follows_phase_order_and_dependencies(tmp_path: Path, git_env: None):
    root = plan_repo(
        tmp_path,
        [
            ok("p5-later", "P5"),
            ok("p1-first", "P1", status="done"),
            ok("p2-needs-first", depends_on=["p1-first"]),
        ],
    )
    found, _ = next_step(load_answers(root / PROJECT))
    assert found is not None and found.id == "p2-needs-first"
    done = run_cli("adopt", "next", str(root))
    assert done.stdout.startswith("Next: p2-needs-first (P2)")
    assert (
        "`true` passes" in done.stdout and "Branch: alpha/p2-needs-first" in done.stdout
    )


def test_next_when_all_done_or_empty(tmp_path: Path, git_env: None):
    root = plan_repo(
        tmp_path,
        [ok("p1-a", "P1", status="dropped", decision=3), ok("p2-b", status="done")],
    )
    _, why = next_step(load_answers(root / PROJECT))
    assert why == "Every step of the adoption plan is done or dropped."
    root = plan_repo(tmp_path / "empty", [])
    _, why = next_step(load_answers(root / PROJECT))
    assert "alpha adopt gaps --save" in why


def test_done_needs_every_condition(tmp_path: Path, git_env: None):
    conditions = [
        {"run": "true"},
        {"run": "sh -c 'echo broken; exit 3'"},
        {"run": "no-such-tool --check"},
        {"recipe": "ml.coverage"},
        {"no_baseline": "typos"},
        {"commit_hook": True},
    ]
    root = plan_repo(
        tmp_path, [step(acceptance=conditions)], baselines=["typos"], git_hooks="chain"
    )
    with pytest.raises(AdoptError) as e:
        done(root, "p2-lint-ml")
    report = str(e.value)
    assert "ok   `true` passes" in report
    assert "exit 3" in report and "broken" in report
    assert "no-such-tool" in report and "exit 127" in report
    assert "ml-python's coverage is still empty" in report
    assert "typos is still in adoption.baselines" in report
    assert "doesn't run alpha's commit check" in report
    assert statuses(root) == {"p2-lint-ml": "pending"}


def test_done_marks_a_step_whose_acceptance_holds(tmp_path: Path, git_env: None):
    root = plan_repo(tmp_path, [ok("p2-a")])
    result = run_cli("adopt", "done", str(root), "p2-a")
    assert result.returncode == 0, result.stderr
    assert "p2-a is done" in result.stdout and "alpha update" in result.stdout
    assert statuses(root) == {"p2-a": "done"}


def test_done_confirm_needs_the_flag(tmp_path: Path, git_env: None):
    root = plan_repo(
        tmp_path, [step(acceptance=[{"confirm": "every error says how to fix it"}])]
    )
    with pytest.raises(AdoptError, match="--confirmed-by-user"):
        done(root, "p2-lint-ml")
    done(root, "p2-lint-ml", confirmed=True)
    assert statuses(root) == {"p2-lint-ml": "done"}


def test_drop_needs_an_accepted_record_naming_the_step(tmp_path: Path, git_env: None):
    root = plan_repo(tmp_path, [ok("p2-a")])
    with pytest.raises(AdoptError, match="No decision record 7"):
        drop(root, "p2-a", "7")
    record = root / "docs/decisions/0007-drop-a.md"
    record.write_text("# 0007. Drop a\n\nStatus: accepted\n\nNot needed.\n")
    with pytest.raises(AdoptError, match="`p2-a`"):
        drop(root, "p2-a", "7")
    record.write_text("# 0007. Drop a\n\nStatus: accepted\n\n`p2-a` isn't needed.\n")
    drop(root, "p2-a", "7")
    saved = json.loads((root / PROJECT).read_text())["adoption"]["steps"][0]
    assert saved["status"] == "dropped" and saved["decision"] == 7


def test_start_sets_in_progress_and_branch(tmp_path: Path, git_env: None):
    root = plan_repo(tmp_path, [ok("p2-a")])
    result = run_cli("adopt", "start", str(root), "p2-a")
    assert "p2-a is in progress on alpha/p2-a" in result.stdout
    saved = json.loads((root / PROJECT).read_text())["adoption"]["steps"][0]
    assert saved["status"] == "in_progress" and saved["branch"] == "alpha/p2-a"


def test_unknown_step_lists_the_ids(tmp_path: Path, git_env: None):
    root = plan_repo(tmp_path, [ok("p2-a")])
    result = run_cli("adopt", "done", str(root), "p9")
    assert result.returncode == 1 and "steps: p2-a" in result.stderr


# --- docs/adoption.md ---

SOURCE = Source(PLUGIN_ROOT, True)
TODAY = date(2026, 11, 11)
PLAN_STEPS = [
    step("p1-format-ml", phase="P1", status="done", title="Format ml in one commit"),
    step("p2-lint-ml", depends_on=["p1-format-ml"], status="in_progress"),
    step(
        "p4-errors",
        phase="P4",
        status="dropped",
        decision=12,
        title="Say how to fix each error",
        acceptance=[{"confirm": "every CLI error says how to fix it"}],
    ),
]


def rendered(root: Path) -> dict[str, str]:
    a = load_answers(root / PROJECT)
    return render_project(root, a, DEFAULTS, 2026, TODAY).texts


def test_adoption_doc_lists_steps_by_phase(tmp_path: Path, git_env: None):
    root = plan_repo(tmp_path, PLAN_STEPS)
    doc = rendered(root)["docs/adoption.md"]
    assert doc.startswith("# Adoption plan\n")
    assert "| P1 Normalize | 1 | 1 |" in doc and "| P4 Rework | 1 | 1 |" in doc
    assert doc.index("## P1 Normalize") < doc.index("## P2 Close tool gaps")
    assert "| `p2-lint-ml` | ml | in progress |" in doc
    assert "After `p1-format-ml`." in doc and "Dropped by decision 0012." in doc
    assert "- the recipe sets ml.commands.lint" in doc
    assert "- the user confirms: every CLI error says how to fix it" in doc


def test_no_adoption_doc_without_steps(tmp_path: Path, git_env: None):
    root = plan_repo(tmp_path, [])
    texts = rendered(root)
    assert "docs/adoption.md" not in texts
    assert "Adoption plan" not in texts["CLAUDE.md"]


def test_claude_md_points_to_the_plan(tmp_path: Path, git_env: None):
    root = plan_repo(tmp_path, PLAN_STEPS)
    assert "- [Adoption plan](docs/adoption.md)" in rendered(root)["CLAUDE.md"]


def test_update_refreshes_the_doc(tmp_path: Path, git_env: None):
    root = plan_repo(tmp_path, [ok("p2-a"), ok("p2-b")])
    plan = plan_adoption(root, PLUGIN_ROOT, SOURCE, TODAY)
    apply_adoption(root, plan)
    for c in plan.update.changes:
        if c.kind == "conflict":
            (root / c.path).write_text((root / PROPOSALS / c.path).read_text())
    commit_update(root, load_project_principles(root), [])
    done(root, "p2-a")
    update = plan_update(root, SOURCE, TODAY)
    assert [c.path for c in update.changes] == ["docs/adoption.md"]
    apply_update(root, update)
    assert "| `p2-a` | ml | done |" in (root / "docs/adoption.md").read_text()


@pytest.mark.slow
def test_adoption_doc_passes_rumdl(tmp_path: Path, git_env: None):
    root = plan_repo(tmp_path, PLAN_STEPS)
    texts = rendered(root)
    for rel in (
        "docs/adoption.md",
        "docs/principles.toml",
        ".rumdl.toml",
        "_typos.toml",
    ):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(texts[rel])
    registry = default_registry()
    for tool in ("rumdl", "typos", "lychee"):
        pin = registry.tool(tool).pin
        assert pin is not None
        command = f"mise x {pin.mise}@{pin.version} -- {pin.command}"
        if tool != "lychee":
            command += " docs/adoption.md"
        else:
            command = command.replace(" .", " docs/adoption.md")
        done_ = subprocess.run(
            command, shell=True, cwd=root, capture_output=True, text=True
        )
        assert done_.returncode == 0, f"{tool}: {done_.stdout}{done_.stderr}"


def _husky(root: Path, line: str) -> None:
    """husky v9's layout: git runs .husky/_/commit-msg, a launcher, which runs
    the user's .husky/commit-msg."""
    for folder, name in (
        ("githooks", "commit-msg"),
        ("hooks", "commit_msg.py"),
        ("hooks", "_common.py"),
    ):
        src = PLUGIN_ROOT / "project-files" / folder / name
        dest = root / ".claude" / "alpha" / folder / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        dest.chmod(0o755)
    launcher = root / ".husky" / "_" / "commit-msg"
    launcher.parent.mkdir(parents=True)
    launcher.write_text('#!/bin/sh\nexec sh .husky/commit-msg "$@"\n')
    launcher.chmod(0o755)
    (root / ".husky" / "commit-msg").write_text(f"echo checking the message\n{line}\n")
    git(root, "config", "core.hooksPath", ".husky/_")


def test_commit_hook_runs_through_a_hook_manager(tmp_path: Path, git_env: None):
    root = plan_repo(
        tmp_path, [step(acceptance=[{"commit_hook": True}])], git_hooks="chain"
    )
    _husky(root, 'sh .claude/alpha/githooks/commit-msg "$1"')
    done(root, "p2-lint-ml")
    assert statuses(root) == {"p2-lint-ml": "done"}


def test_commit_hook_missing_from_the_hook_manager(tmp_path: Path, git_env: None):
    root = plan_repo(
        tmp_path, [step(acceptance=[{"commit_hook": True}])], git_hooks="chain"
    )
    _husky(root, "exit 0")
    with pytest.raises(AdoptError, match="doesn't run alpha's commit check"):
        done(root, "p2-lint-ml")


def test_survey_hook_files_reach_the_principles(tmp_path: Path, git_env: None):
    survey = {"git": {"hook_managers": [".husky/commit-msg"]}}
    root = plan_repo(tmp_path, [], git_hooks="chain", survey=survey)
    principles = tomllib.loads(rendered(root)["docs/principles.toml"])
    assert principles["git"]["hook_files"] == [".husky/commit-msg"]
