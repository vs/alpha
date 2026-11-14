"""The Rust recipe's gates: branch coverage on a dated nightly (decision 0028)."""

import json
import tomllib
from pathlib import Path
from typing import Any

import yaml
from helpers import TODAY, place_answers

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
