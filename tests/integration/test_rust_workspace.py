"""A monorepo's Rust components as one Cargo workspace."""

import json
import tomllib
from pathlib import Path
from typing import Any

import yaml
from helpers import TODAY, git, install, place_answers, place_rust_monorepo

from alpha import apply
from alpha.apply import describe
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import load_project_principles
from alpha.gitops import commit

SOURCE = Source(PLUGIN_ROOT, True)
ROOT_FILES = {"Cargo.toml", "clippy.toml", "rust-toolchain.toml"}


def generated(target: Path, **testing: bool) -> dict[str, Any]:
    place_rust_monorepo(target, **testing)
    install(target)
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


def test_R17_2_a_workspace_member_runs_by_its_answer_and_keeps_its_workspace(
    tmp_path: Path,
):
    answers = place_rust_monorepo(tmp_path)
    data = json.loads(answers.read_text())
    run = "cargo run -p tidy-cli -- build"
    data["components"][0]["run"] = run
    answers.write_text(json.dumps(data))
    install(tmp_path)
    components = by_name(load_project_principles(tmp_path))
    assert components["cli"]["commands"]["run"] == run
    assert components["core"]["commands"]["run"] == ""
    assert components["cli"]["workspace"] == sorted(ROOT_FILES)
    root = tomllib.loads((tmp_path / "Cargo.toml").read_text())
    assert root["workspace"]["members"] == ["cli", "core"]
    assert f"| run | `{run}` |" in (tmp_path / "CLAUDE.md").read_text()
    assert run in (tmp_path / "README.md").read_text()
    for never in (".github/workflows/ci.yml", "mise.toml"):
        assert "cargo run" not in (tmp_path / never).read_text(), never


def generate_files(target: Path) -> set[str]:
    place_rust_monorepo(target)
    return set(install(target))


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
    assert ignored.count("/target/") == 1
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
    files = set(install(tmp_path))
    assert not ROOT_FILES & files
    assert {"core/Cargo.toml", "core/clippy.toml", "core/rust-toolchain.toml"} <= files
    core = by_name(load_project_principles(tmp_path))["core"]
    assert core["lockfiles"] == ["core/Cargo.lock"] and "workspace" not in core
    assert "core/**/target/" in (tmp_path / ".gitignore").read_text().splitlines()


def test_single_layout_keeps_the_single_crate_files(tmp_path: Path):
    place_answers(tmp_path, "rust-cli")
    install(tmp_path)
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
    commit(tmp_path, principles, [])
    assert git(tmp_path, "status", "--porcelain") == ""
    subject = "build: Set up the rust workspace and tests"
    made = git(tmp_path, "log", "--format=%H", f"--grep={subject}")
    changed = git(tmp_path, "show", "--name-only", "--format=", made).splitlines()
    assert {*ROOT_FILES, "Cargo.lock", "cli/Cargo.toml", "core/Cargo.toml"} <= set(
        changed
    )
    assert not [f for f in changed if f.startswith("api/")]


def test_update_moves_separate_crates_into_the_workspace(tmp_path: Path, git_env: None):
    answers = place_rust_monorepo(tmp_path, workspace=False)
    install(tmp_path)
    for member in ("cli", "core"):
        (tmp_path / member / "Cargo.lock").write_text("version = 4\n")
    commit(tmp_path, load_project_principles(tmp_path), [])
    data = json.loads(answers.read_text())
    del data["workspace"]
    answers.write_text(json.dumps(data))

    plan = apply.plan(tmp_path, PLUGIN_ROOT, SOURCE, TODAY)
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

    apply.write(tmp_path, plan)
    (tmp_path / "Cargo.lock").write_text("version = 4\n")  # the setup command's
    commit(tmp_path, load_project_principles(tmp_path), [])
    tracked = git(tmp_path, "ls-files").splitlines()
    assert {*ROOT_FILES, "Cargo.lock"} <= set(tracked)
