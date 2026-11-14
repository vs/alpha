"""The Rust recipe's gates: branch coverage on a dated nightly (decision 0028)
and mutation testing for an exhaustive project (decision 0029)."""

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from helpers import TODAY, place_answers, place_rust_monorepo

from alpha.answers import AnswersError
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import generate, load_project_principles

SOURCE = Source(PLUGIN_ROOT, True)
RECIPE = PLUGIN_ROOT / "recipes/rust.toml"


def rust_cli(target: Path, **testing: object) -> dict[str, Any]:
    """The single-crate scenario, generated; `testing` sets answers of the
    testing area."""
    answers = place_answers(target, "rust-cli")
    data = json.loads(answers.read_text())
    data["testing"].update(testing)
    answers.write_text(json.dumps(data))
    generate(target, PLUGIN_ROOT, SOURCE, 2026, TODAY)
    return load_project_principles(target)


def steps(target: Path, job: str) -> list[dict[str, Any]]:
    workflow = yaml.safe_load((target / ".github/workflows/ci.yml").read_text())
    return workflow["jobs"][job]["steps"]


def named(target: Path, job: str) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in steps(target, job) if "name" in s}


def test_coverage_runs_on_the_recipe_s_dated_nightly(tmp_path: Path):
    rust_cli(tmp_path)
    nightly = tomllib.loads(RECIPE.read_text())["vars"]["coverage_toolchain"]
    assert nightly.startswith("nightly-20")
    assert RECIPE.read_text().count(nightly) == 1  # the rest name the variable
    cli = named(tmp_path, "cli")
    assert cli["test with coverage"]["run"] == (
        f"cargo +{nightly} llvm-cov --branch --cobertura --output-path coverage.xml"
    )
    assert cli["test"]["run"] == "cargo test"  # the pinned stable toolchain
    installs = [
        s["with"] for s in steps(tmp_path, "cli") if s.get("with", {}).get("toolchain")
    ]
    assert installs == [
        {
            "toolchain": nightly,
            "components": "llvm-tools-preview",
            "override": "false",
            "cache": "false",
        }
    ]
    # Branches are recorded either way; the gate reads them only when exhaustive.
    assert "--branch-coverage" not in cli["diff coverage"]["run"]
    rust_cli(tmp_path / "exhaustive", exhaustive=True)
    gate = named(tmp_path / "exhaustive", "cli")["diff coverage"]["run"]
    assert gate.endswith("--fail-under=100 --branch-coverage")


def test_exhaustive_rust_component_gets_the_mutants_gate(tmp_path: Path):
    principles = rust_cli(tmp_path, exhaustive=True)
    (cli,) = principles["components"]
    command = cli["mutants"]
    assert command.startswith("cargo mutants --in-diff pr.diff --in-place --timeout-")
    assert command.endswith("|| [ $? -eq 3 ]")  # a timed-out mutant is caught
    step = named(tmp_path, "cli")["mutants"]
    assert step["if"] == "github.event_name == 'pull_request'"
    assert step["env"] == {"BASE_REF": "${{ github.base_ref }}"}
    assert step["run"] == (
        f'git diff --relative "origin/${{BASE_REF}}"...HEAD > pr.diff && {command}'
    )
    assert steps(tmp_path, "cli")[0]["with"]["fetch-depth"] == 0  # for the diff
    mise = tomllib.loads((tmp_path / "mise.toml").read_text())["tasks"]
    task = mise["check:mutants:cli"]
    assert task["dir"] == "."
    assert task["run"].startswith('if [ -z "${ALPHA_BASE:-}" ] || [ -n "${CI:-}" ]')
    assert (
        f'git diff --relative "$ALPHA_BASE"...HEAD > pr.diff && {command}'
        in (task["run"])
    )
    assert "check:mutants:cli" in mise["ci"]["depends"]
    settings = json.loads((tmp_path / ".claude/settings.json").read_text())
    assert "Bash(cargo mutants:*)" in settings["permissions"]["allow"]
    ignored = (tmp_path / ".gitignore").read_text().splitlines()
    assert {"mutants.out*/", "pr.diff"} <= set(ignored)
    exhaustive = next(
        p for p in principles["principles"] if p["id"] == "exhaustive-testing"
    )
    assert "ci:mutants" in exhaustive["checked_by"]
    assert (
        "Every changed line's mutants are caught by a test."
        in (exhaustive["statement"])
    )
    contributing = (tmp_path / "CONTRIBUTING.md").read_text()
    assert "`ci:mutants` is when" in contributing
    assert "**Mutants are caught.** In cli, a pull request fails" in contributing
    assert "#[mutants::skip]" in (tmp_path / "CLAUDE.md").read_text()


def test_mutants_gate_follows_exhaustive_testing_and_its_answer(tmp_path: Path):
    (standard,) = rust_cli(tmp_path / "standard")["components"]
    assert "mutants" not in standard
    assert "mutants" not in named(tmp_path / "standard", "cli")
    declined = rust_cli(tmp_path / "declined", exhaustive=True, mutants=False)
    assert "mutants" not in declined["components"][0]
    with pytest.raises(AnswersError, match="part of exhaustive testing"):
        rust_cli(tmp_path / "alone", mutants=True)


def test_only_a_stack_with_a_mutants_command_is_gated(tmp_path: Path):
    place_rust_monorepo(tmp_path, exhaustive=True)
    generate(tmp_path, PLUGIN_ROOT, SOURCE, 2026, TODAY)
    gated = {
        c["name"]: "mutants" in c
        for c in load_project_principles(tmp_path)["components"]
    }
    assert gated == {"cli": True, "core": True, "api": False}  # api is Python
    assert "mutants" not in named(tmp_path, "api")
