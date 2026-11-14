"""A monorepo's Rust components as one Cargo workspace (decision 0027)."""

import json
import tomllib
from pathlib import Path
from typing import Any

import yaml
from helpers import TODAY, git, place_answers, place_rust_monorepo

from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import generate, load_project_principles
from alpha.gitops import commit_skeleton, commit_update
from alpha.update import apply_update, describe, plan_update

SOURCE = Source(PLUGIN_ROOT, True)
ROOT_FILES = {"Cargo.toml", "clippy.toml", "rust-toolchain.toml"}


def generated(target: Path, **testing: bool) -> dict[str, Any]:
    place_rust_monorepo(target, **testing)
    generate(target, PLUGIN_ROOT, SOURCE, 2026, TODAY)
    return load_project_principles(target)


def by_name(principles: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in principles["components"]}


def jobs(target: Path) -> dict[str, dict[str, Any]]:
    workflow = yaml.safe_load((target / ".github/workflows/ci.yml").read_text())
    return {
        name: {s.get("name", s.get("uses", "")): s for s in job["steps"]}
        for name, job in workflow["jobs"].items()
    }


def test_rust_components_of_a_monorepo_form_one_workspace(tmp_path: Path):
    files = generate_files(tmp_path)
    assert ROOT_FILES <= files
    for member in ("cli", "core"):
        assert {f"{member}/Cargo.toml", f"{member}/tests/setup.rs"} <= files
        assert f"{member}/clippy.toml" not in files
        assert f"{member}/rust-toolchain.toml" not in files
    root = tomllib.loads((tmp_path / "Cargo.toml").read_text())
    assert "package" not in root
    workspace = root["workspace"]
    assert workspace["members"] == ["cli", "core"]  # the Python component isn't one
    assert workspace["resolver"] == "3"
    assert workspace["package"] == {
        "edition": "2024",
        "version": "0.1.0",
        "publish": False,
    }
    assert workspace["dependencies"] == {}
    assert workspace["lints"]["rust"] == {"unsafe_code": "forbid"}
    single = tomllib.loads((PLUGIN_ROOT / "recipes/rust/Cargo.toml.tmpl").read_text())
    assert workspace["lints"] == single["lints"]  # moved, unchanged
    member = tomllib.loads((tmp_path / "core/Cargo.toml").read_text())
    assert member == {
        "package": {
            "name": "tidy-core",
            "version": {"workspace": True},
            "edition": {"workspace": True},
            "publish": {"workspace": True},
        },
        "dependencies": {},
        "lints": {"workspace": True},
    }
    setup = (tmp_path / "core/tests/setup.rs").read_text()
    assert 'include_str!("../../Cargo.toml")' in setup  # the root's lints
    assert 'include_str!("../Cargo.toml")' in setup  # its own [lints]


def generate_files(target: Path) -> set[str]:
    place_rust_monorepo(target)
    return set(generate(target, PLUGIN_ROOT, SOURCE, 2026, TODAY))


def test_workspace_root_holds_the_lockfile_ignores_and_updates(tmp_path: Path):
    principles = generated(tmp_path)
    components = by_name(principles)
    for member in ("cli", "core"):
        assert components[member]["lockfiles"] == ["Cargo.lock"]
        assert components[member]["manifests"] == [f"{member}/Cargo.toml", "Cargo.toml"]
        assert components[member]["workspace"] == sorted(ROOT_FILES)
        rules = {r["id"]: r["rule"] for r in components[member]["rules"]}
        assert rules["rust:cargo-for-dependencies"].startswith(
            "Declare each dependency once, in `[workspace.dependencies]`"
        )
    assert "workspace" not in components["api"]
    assert components["api"]["lockfiles"] == ["api/uv.lock"]
    protected = principles["protected"]["paths"]
    assert "Cargo.lock" in protected and "cli/Cargo.lock" not in protected
    ignored = (tmp_path / ".gitignore").read_text().splitlines()
    assert ignored.count("/target/") == 1 and "/mutants.out*/" in ignored
    assert "cli/**/coverage.xml" in ignored
    assert not [
        line for line in ignored if line.endswith("/target/") and line[0] != "/"
    ]
    dependabot = yaml.safe_load((tmp_path / ".github/dependabot.yml").read_text())
    cargo = [u for u in dependabot["updates"] if u["package-ecosystem"] == "cargo"]
    assert [u["directory"] for u in cargo] == ["/"]
    for member in ("cli", "core"):
        steps = jobs(tmp_path)[member]
        cached = [s for s in steps.values() if "cache-workspaces" in s.get("with", {})]
        assert [s["with"]["cache-workspaces"] for s in cached] == ["."]
        assert cached[0]["with"]["rust-src-dir"] == "."
    vulns = next(c for c in principles["repo_checks"] if c["id"] == "vulns")
    assert vulns["globs"] == ["Cargo.lock", "api/uv.lock"]
    lychee = tomllib.loads((tmp_path / "lychee.toml").read_text())["exclude_path"]
    assert r"^(?:\./)?target/" in lychee  # the root's only, not api/target/


def test_workspace_answer_keeps_each_component_a_crate(tmp_path: Path):
    place_rust_monorepo(tmp_path, workspace=False)
    files = set(generate(tmp_path, PLUGIN_ROOT, SOURCE, 2026, TODAY))
    assert not ROOT_FILES & files
    assert {"core/Cargo.toml", "core/clippy.toml", "core/rust-toolchain.toml"} <= files
    core = by_name(load_project_principles(tmp_path))["core"]
    assert core["lockfiles"] == ["core/Cargo.lock"] and "workspace" not in core
    assert "core/**/target/" in (tmp_path / ".gitignore").read_text().splitlines()


def test_single_layout_keeps_the_single_crate_files(tmp_path: Path):
    place_answers(tmp_path, "rust-cli")
    generate(tmp_path, PLUGIN_ROOT, SOURCE, 2026, TODAY)
    cargo = tomllib.loads((tmp_path / "Cargo.toml").read_text())
    assert "workspace" not in cargo and cargo["package"]["edition"] == "2024"
    assert cargo["lints"]["rust"] == {"unsafe_code": "forbid"}
    (cli,) = load_project_principles(tmp_path)["components"]
    assert cli["lockfiles"] == ["Cargo.lock"] and "workspace" not in cli
    assert (
        cli["commands"]["lint"] == "cargo clippy --all-targets --no-deps -- -D warnings"
    )
    rules = {r["id"]: r["rule"] for r in cli["rules"]}
    assert rules["rust:cargo-for-dependencies"].startswith(
        "Add and remove dependencies"
    )


def test_skeleton_commits_a_workspace_with_its_members(tmp_path: Path, git_env: None):
    principles = generated(tmp_path)
    (tmp_path / "Cargo.lock").write_text("version = 4\n")  # as cargo fetch writes
    commit_skeleton(tmp_path, principles, [])
    assert git(tmp_path, "status", "--porcelain") == ""
    subject = "build: Set up the rust workspace and tests"
    commit = git(tmp_path, "log", "--format=%H", f"--grep={subject}")
    changed = git(tmp_path, "show", "--name-only", "--format=", commit).splitlines()
    assert {*ROOT_FILES, "Cargo.lock", "cli/Cargo.toml", "core/Cargo.toml"} <= set(
        changed
    )
    assert not [f for f in changed if f.startswith("api/")]


def test_update_moves_separate_crates_into_the_workspace(tmp_path: Path, git_env: None):
    answers = place_rust_monorepo(tmp_path, workspace=False)
    generate(tmp_path, PLUGIN_ROOT, SOURCE, 2026, TODAY)
    for member in ("cli", "core"):
        (tmp_path / member / "Cargo.lock").write_text("version = 4\n")
    commit_skeleton(tmp_path, load_project_principles(tmp_path), [])
    data = json.loads(answers.read_text())
    del data["workspace"]
    answers.write_text(json.dumps(data))

    plan = plan_update(tmp_path, PLUGIN_ROOT, SOURCE, TODAY)
    kinds = {c.path: c.kind for c in plan.changes}
    assert {kinds[f] for f in ROOT_FILES} == {"new"}
    assert kinds["core/Cargo.toml"] == "change"
    assert kinds["core/rust-toolchain.toml"] == kinds["core/clippy.toml"] == "stale"
    text = describe(plan, tmp_path)
    for member in ("cli", "core"):
        assert (
            f"stale     {member}/Cargo.lock ({member} now locks its dependencies in "
            "Cargo.lock: delete this file and the build output beside it; "
            "`cargo fetch` writes Cargo.lock)"
        ) in text

    apply_update(tmp_path, plan)
    (tmp_path / "Cargo.lock").write_text("version = 4\n")  # the setup command's
    commit_update(tmp_path, load_project_principles(tmp_path), [])
    tracked = git(tmp_path, "ls-files").splitlines()
    assert {*ROOT_FILES, "Cargo.lock"} <= set(tracked)


def test_member_s_mutants_diff_names_files_from_the_workspace_root(tmp_path: Path):
    generated(tmp_path, exhaustive=True)
    step = jobs(tmp_path)["core"]["mutants"]
    # cargo-mutants mutates the workspace's tree, whose root is the repository's.
    assert step["run"].startswith('git diff "origin/${BASE_REF}"...HEAD > pr.diff && ')
    mise = tomllib.loads((tmp_path / "mise.toml").read_text())["tasks"]
    assert (
        'git diff "$ALPHA_BASE"...HEAD > pr.diff' in mise["check:mutants:core"]["run"]
    )
    assert {"check:mutants:cli", "check:mutants:core"} <= set(mise["ci"]["depends"])
    # One tree, mutated in place: the members' runs never overlap.
    assert "depends" not in mise["check:mutants:cli"]
    assert mise["check:mutants:core"]["depends"] == ["check:mutants:cli"]
