import json
import os
import shutil
import subprocess
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from helpers import TODAY, GenerateScenario, git, place_answers

from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import bootstrap, generate, project_book
from alpha.gitops import commit_skeleton
from alpha.registry import load_registry
from alpha_evals.seeded import REPO_SEEDS as SEEDS

NEEDS_CARGO = pytest.mark.skipif(
    shutil.which("cargo") is None, reason="needs the Rust toolchain (cargo)"
)


@pytest.mark.slow
@pytest.mark.parametrize(
    "scenario",
    [
        "python-ml-single",
        "web-ts-plus-python-api",
        pytest.param("rust-cli", marks=NEEDS_CARGO),
    ],
)
def test_bootstrap_runs_green(
    tmp_path: Path, scenario: str, generate_scenario: GenerateScenario, git_env: None
):
    """R2: generate and bootstrap leave a skeleton whose checks all pass."""
    generate_scenario(tmp_path, scenario)
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    for c in principles["components"]:
        for lockfile in project_book(tmp_path).get(c["stack"]).lockfiles:
            assert (tmp_path / c["path"] / lockfile).is_file()

    commit_skeleton(tmp_path, principles, [])
    assert git(tmp_path, "status", "--porcelain") == ""
    tracked = git(tmp_path, "ls-files").splitlines()
    for c in principles["components"]:
        for lockfile in project_book(tmp_path).get(c["stack"]).lockfiles:
            prefix = "" if c["path"] == "." else f"{c['path']}/"
            assert f"{prefix}{lockfile}" in tracked
    junk = (".venv/", "__pycache__/", ".pytest_cache/", "node_modules/", "target/")
    assert not [f for f in tracked if any(j in f"/{f}" for j in junk)]

    for c in principles["components"]:
        for name in ("lint", "typecheck", "format"):
            command = c["commands"][name]
            done = subprocess.run(
                command,
                shell=True,
                cwd=tmp_path / c["path"],
                capture_output=True,
                text=True,
            )
            output = done.stdout + done.stderr
            assert done.returncode == 0, f"{command}: {output}"
            assert "deprecat" not in output.lower(), f"{command}: {output}"
    assert git(tmp_path, "status", "--porcelain") == ""


UNFORMATTED = {
    "python": ("bad.py", "x  =  1\n"),
    "typescript": ("bad.ts", "const x={a:1}\n"),
}


@pytest.mark.slow
def test_format_check_fails_on_an_unformatted_file(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    for c in principles["components"]:
        name, text = UNFORMATTED[c["stack"]]
        bad = tmp_path / c["path"] / name
        bad.write_text(text)
        done = subprocess.run(
            c["commands"]["format_check"],
            shell=True,
            cwd=tmp_path / c["path"],
            capture_output=True,
            text=True,
        )
        assert done.returncode != 0, f"{c['name']}: {done.stdout}{done.stderr}"
        assert bad.read_text() == text, f"{c['name']}: format_check rewrote {name}"


@pytest.mark.slow
def test_typescript_at_the_root_runs_green(tmp_path: Path, git_env: None):
    answers = place_answers(tmp_path, "python-ml-single")
    data = json.loads(answers.read_text())
    data["components"][0].update(stack="typescript", kind="cli")
    answers.write_text(json.dumps(data))
    generate(tmp_path, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), 2026, TODAY)
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    commit_skeleton(tmp_path, principles, [])
    assert git(tmp_path, "status", "--porcelain") == ""


def mise_run(cwd: Path, task: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["mise", "run", task], cwd=cwd, capture_output=True, text=True
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    "scenario",
    [
        "python-ml-single",
        "web-ts-plus-python-api",
        pytest.param("rust-cli", marks=NEEDS_CARGO),
    ],
)
def test_scenarios_pass_repo_checks(
    tmp_path: Path, scenario: str, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, scenario)
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)  # raises unless `mise run ci` exits 0
    # commit-skeleton's own git init must leave bootstrap's repository usable.
    git(tmp_path, "init", "-q", "-b", "main")
    commit_skeleton(tmp_path, principles, [])
    assert git(tmp_path, "status", "--porcelain") == ""
    done = mise_run(tmp_path, "ci")
    assert done.returncode == 0, done.stdout + done.stderr
    assert git(tmp_path, "status", "--porcelain") == ""


@pytest.fixture(scope="module")
def bootstrapped_web(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("web")
    place_answers(target, "web-ts-plus-python-api")
    generate(target, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), 2026, TODAY)
    bootstrap(target, tomllib.loads((target / "docs/principles.toml").read_text()))
    return target


@pytest.fixture
def seeded(
    bootstrapped_web: Path, request: pytest.FixtureRequest
) -> Iterator[tuple[str, Path]]:
    """The seed's check and the bootstrapped project with the seed applied,
    reverted afterwards."""
    check: str = request.param
    _, rel, change, _ = SEEDS[check]
    path = bootstrapped_web / rel
    before = path.read_text() if path.exists() else None
    after = change(before)
    assert after != before, f"the {check} seed changed nothing"
    path.write_text(after)
    try:
        yield check, bootstrapped_web
    finally:
        if before is None:
            path.unlink()
        else:
            path.write_text(before)


@pytest.mark.slow
@pytest.mark.parametrize("seeded", list(SEEDS), indirect=True)
def test_repo_checks_can_fail(seeded: tuple[str, Path]):
    check, project = seeded
    pin = load_registry(Source(PLUGIN_ROOT, True)).tool(SEEDS[check][0]).pin
    assert pin is not None
    done = mise_run(project, f"check:{check}")
    output = done.stdout + done.stderr
    # mise run passes the task's exit code through unchanged.
    assert done.returncode == pin.fails_with, output
    assert SEEDS[check][3] in output, output


def _sh(
    command: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, shell=True, cwd=cwd, capture_output=True, text=True, env=env
    )


@pytest.mark.slow
def test_structure_fails_on_unused_dependency(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    unused = {"python": "uv add requests", "typescript": "pnpm add left-pad"}
    for c in principles["components"]:
        cwd = tmp_path / c["path"]
        command = c["commands"]["structure"]

        assert _sh(command, cwd).returncode == 0, c["name"]
        files = [cwd / "pyproject.toml", cwd / "package.json"]
        lockfiles = [cwd / "uv.lock", cwd / "pnpm-lock.yaml"]
        saved = {f: f.read_bytes() for f in [*files, *lockfiles] if f.exists()}
        add = _sh(unused[c["stack"]], cwd)
        assert add.returncode == 0, add.stdout + add.stderr
        done = _sh(command, cwd)
        assert done.returncode != 0, f"{c['name']}: {done.stdout}{done.stderr}"
        for f, data in saved.items():  # revert, so the tree is as it was
            f.write_bytes(data)


@pytest.mark.slow
def test_depcruise_reports_a_cycle(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    web = tmp_path / "web"
    command = "pnpm depcruise --config .dependency-cruiser.cjs ."
    assert _sh(command, web).returncode == 0
    seeds = {
        web / "src/a.ts": 'import "./b.js";\nexport const a = 1;\n',
        web / "src/b.ts": 'import "./a.js";\nexport const b = 1;\n',
    }
    try:
        (web / "src").mkdir()
        for path, text in seeds.items():
            path.write_text(text)
        done = _sh(command, web)
        output = done.stdout + done.stderr
        assert done.returncode != 0, output
        assert "no-circular" in output, output
    finally:
        for path in seeds:
            path.unlink(missing_ok=True)
        (web / "src").rmdir()


@pytest.mark.slow
def test_diff_cover_catches_untested_line(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    commit_skeleton(tmp_path, principles, [])
    git(tmp_path, "branch", "-M", "main")  # CI compares against origin/<base>
    git(tmp_path, "switch", "-c", "feature")

    workflow = yaml.safe_load((tmp_path / ".github/workflows/ci.yml").read_text())
    steps = {s.get("name"): s for s in workflow["jobs"]["api"]["steps"]}
    coverage = steps["test with coverage"]["run"]
    # The same command CI runs; the registry pin comes through `uvx` here, since
    # pipx may not be installed, and the base is the local branch.
    diff = (
        steps["diff coverage"]["run"]
        .replace("pipx run", "uvx")
        .replace("origin/${BASE_REF}", "${BASE_REF}")  # no remote here
    )
    diff_env = {**os.environ, "BASE_REF": "main"}  # CI's base_ref; local branch
    pin = load_registry(Source(PLUGIN_ROOT, True)).tool("diff-cover").pin
    assert pin is not None
    assert f"diff-cover=={pin.version}" in diff

    api = tmp_path / "api"
    (api / "app").mkdir(exist_ok=True)
    (api / "app/x.py").write_text(
        "def double(n: int) -> int:\n    total = n * 2\n    return total\n"
    )
    (api / "tests").mkdir(exist_ok=True)
    (api / "tests/helper_unimported.py").write_text("VALUE = 1\n")
    git(tmp_path, "add", "api/app/x.py", "api/tests/helper_unimported.py")
    git(tmp_path, "commit", "-m", "feat(api): Add double", "--no-verify")

    done = _sh(coverage, api)
    assert done.returncode == 0, done.stdout + done.stderr
    report = (api / "coverage.xml").read_text()
    assert 'filename="app/x.py"' in report  # unimported source counts
    assert "helper_unimported" not in report  # tests and helpers don't
    assert "test_setup.py" not in report
    done = _sh(diff, api, diff_env)
    output = done.stdout + done.stderr
    assert done.returncode != 0, output
    assert "x.py" in output, output

    (api / "tests").mkdir(exist_ok=True)
    (api / "tests/test_x.py").write_text(
        "import sys\nfrom pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).parents[1]))\n"
        "from app.x import double  # noqa: E402\n\n\n"
        "def test_double() -> None:\n    assert double(2) == 4\n"
    )
    git(tmp_path, "add", "api/tests/test_x.py")
    git(tmp_path, "commit", "-m", "test(api): Cover double", "--no-verify")
    assert _sh(coverage, api).returncode == 0
    done = _sh(diff, api, diff_env)
    assert done.returncode == 0, done.stdout + done.stderr
    # The report files are ignored, so CI's tree check still passes.
    assert git(tmp_path, "status", "--porcelain") == ""


@pytest.mark.slow
def test_diff_cover_catches_untested_typescript_line(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    commit_skeleton(tmp_path, principles, [])
    git(tmp_path, "branch", "-M", "main")
    git(tmp_path, "switch", "-c", "feature")

    workflow = yaml.safe_load((tmp_path / ".github/workflows/ci.yml").read_text())
    steps = {s.get("name"): s for s in workflow["jobs"]["web"]["steps"]}
    coverage = steps["test with coverage"]["run"]
    diff = (
        steps["diff coverage"]["run"]
        .replace("pipx run", "uvx")
        .replace("origin/${BASE_REF}", "${BASE_REF}")
    )
    diff_env = {**os.environ, "BASE_REF": "main"}

    web = tmp_path / "web"
    (web / "src").mkdir(exist_ok=True)
    (web / "src/x.ts").write_text(
        "export function double(n: number): number {\n"
        "  const total = n * 2;\n"
        "  return total;\n"
        "}\n"
    )
    (web / "other.config.ts").write_text("export default { name: 'x' };\n")
    git(tmp_path, "add", "web/src/x.ts", "web/other.config.ts")
    git(tmp_path, "commit", "-m", "feat(web): Add double", "--no-verify")

    done = _sh(coverage, web)
    assert done.returncode == 0, done.stdout + done.stderr
    report = (web / "coverage/cobertura-coverage.xml").read_text()
    assert "src/x.ts" in report  # unimported source counts
    assert "other.config" not in report  # config files don't
    assert "setup.test.ts" not in report  # tests don't
    done = _sh(diff, web, diff_env)
    output = done.stdout + done.stderr
    assert done.returncode != 0, output
    assert "x.ts" in output, output

    (web / "tests/x.test.ts").write_text(
        'import { expect, test } from "vitest";\n'
        'import { double } from "../src/x.js";\n\n'
        'test("double", () => {\n  expect(double(2)).toBe(4);\n});\n'
    )
    git(tmp_path, "add", "web/tests/x.test.ts")
    git(tmp_path, "commit", "-m", "test(web): Cover double", "--no-verify")
    assert _sh(coverage, web).returncode == 0
    done = _sh(diff, web, diff_env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert git(tmp_path, "status", "--porcelain") == ""


_HALF_TESTED_BRANCH = {
    "api": (
        "app/clamp.py",
        "def clamp(n: int) -> int:\n"
        "    total = n\n"
        "    if n < 0:\n"
        "        total = 0\n"
        "    return total\n",
        "tests/test_clamp.py",
        "import sys\nfrom pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).parents[1]))\n"
        "from app.clamp import clamp\n\n\n"
        "def test_clamp() -> None:\n    assert clamp(-1) == 0\n",
        "\n\ndef test_clamp_keeps() -> None:\n    assert clamp(2) == 2\n",
    ),
    "web": (
        "src/clamp.ts",
        "export function clamp(n: number): number {\n"
        "  let total = n;\n"
        "  if (n < 0) {\n"
        "    total = 0;\n"
        "  }\n"
        "  return total;\n"
        "}\n",
        "tests/clamp.test.ts",
        'import { expect, test } from "vitest";\n'
        'import { clamp } from "../src/clamp.js";\n\n'
        'test("clamp", () => {\n  expect(clamp(-1)).toBe(0);\n});\n',
        '\ntest("clamp keeps", () => {\n  expect(clamp(2)).toBe(2);\n});\n',
    ),
}


@pytest.mark.slow
def test_exhaustive_gate_catches_a_half_tested_branch(tmp_path: Path, git_env: None):
    answers = place_answers(tmp_path, "web-ts-plus-python-api")
    data = json.loads(answers.read_text())
    data["testing"]["exhaustive"] = True
    answers.write_text(json.dumps(data))
    generate(tmp_path, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), 2026, TODAY)
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    commit_skeleton(tmp_path, principles, [])
    git(tmp_path, "branch", "-M", "main")
    git(tmp_path, "switch", "-c", "feature")
    workflow = yaml.safe_load((tmp_path / ".github/workflows/ci.yml").read_text())
    diff_env = {**os.environ, "BASE_REF": "main"}

    for name, (source, code, test, one_side, other_side) in _HALF_TESTED_BRANCH.items():
        steps = {s.get("name"): s for s in workflow["jobs"][name]["steps"]}
        coverage = steps["test with coverage"]["run"]
        assert steps["diff coverage"]["run"].endswith("--branch-coverage")
        diff = (
            steps["diff coverage"]["run"]
            .replace("pipx run", "uvx")
            .replace("origin/${BASE_REF}", "${BASE_REF}")
        )
        folder = tmp_path / name
        (folder / source).parent.mkdir(exist_ok=True)
        (folder / source).write_text(code)
        (folder / test).write_text(one_side)
        git(tmp_path, "add", f"{name}/{source}", f"{name}/{test}")
        git(tmp_path, "commit", "-m", f"feat({name}): Add clamp", "--no-verify")

        done = _sh(coverage, folder)
        assert done.returncode == 0, done.stdout + done.stderr
        # Every line ran, so only the untaken side of the `if` fails the gate.
        lines_only = _sh(diff.removesuffix(" --branch-coverage"), folder, diff_env)
        assert lines_only.returncode == 0, lines_only.stdout + lines_only.stderr
        done = _sh(diff, folder, diff_env)
        output = done.stdout + done.stderr
        assert done.returncode != 0, output
        assert "clamp" in output, output

        (folder / test).write_text(one_side + other_side)
        git(tmp_path, "add", f"{name}/{test}")
        git(tmp_path, "commit", "-m", f"test({name}): Cover both sides", "--no-verify")
        assert _sh(coverage, folder).returncode == 0
        done = _sh(diff, folder, diff_env)
        assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.slow
@NEEDS_CARGO
def test_rust_checks_fail_on_their_violations(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "rust-cli")
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    commit_skeleton(tmp_path, principles, [])
    (cli,) = principles["components"]
    commands = cli["commands"]
    cwd = tmp_path / cli["path"]
    saved = {f: f.read_bytes() for f in (cwd / "Cargo.toml", cwd / "Cargo.lock")}

    def fails(step: str) -> str:
        done = _sh(commands[step], cwd)
        output = done.stdout + done.stderr
        assert done.returncode != 0, f"{step}: {output}"
        return output

    bad = cwd / "tests/bad.rs"
    bad.write_text("#[test]\nfn  t( ) {}\n")
    fails("format_check")
    assert bad.read_text() == "#[test]\nfn  t( ) {}\n"
    bad.unlink()

    (cwd / "src").mkdir()
    (cwd / "src/lib.rs").write_text(
        '//! x\n\n#[must_use]\npub fn n() -> u8 {\n    "1".parse().unwrap()\n}\n'
    )
    assert "clippy::unwrap_used" in fails("lint")
    (cwd / "src/lib.rs").unlink()
    (cwd / "src").rmdir()

    assert _sh("cargo add itoa@1", cwd).returncode == 0
    assert "itoa" in fails("structure")
    for f, data in saved.items():
        f.write_bytes(data)
    assert git(tmp_path, "status", "--porcelain") == ""


@pytest.mark.slow
@NEEDS_CARGO
def test_diff_cover_catches_untested_rust_line(
    tmp_path: Path, generate_scenario: GenerateScenario, git_env: None
):
    generate_scenario(tmp_path, "rust-cli")
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    commit_skeleton(tmp_path, principles, [])
    git(tmp_path, "branch", "-M", "main")
    git(tmp_path, "switch", "-c", "feature")

    workflow = yaml.safe_load((tmp_path / ".github/workflows/ci.yml").read_text())
    steps = {s.get("name"): s for s in workflow["jobs"]["cli"]["steps"]}
    coverage = steps["test with coverage"]["run"]
    diff = (
        steps["diff coverage"]["run"]
        .replace("pipx run", "uvx")
        .replace("origin/${BASE_REF}", "${BASE_REF}")
    )
    diff_env = {**os.environ, "BASE_REF": "main"}

    (tmp_path / "src").mkdir()
    (tmp_path / "src/lib.rs").write_text("//! Tidy.\n\npub mod double;\n")
    (tmp_path / "src/double.rs").write_text(
        "//! Doubling.\n\n/// Twice `n`.\n#[must_use]\n"
        "pub fn double(n: u32) -> u32 {\n    n * 2\n}\n"
    )
    git(tmp_path, "add", "src")
    git(tmp_path, "commit", "-m", "feat(cli): Add double", "--no-verify")

    done = _sh(coverage, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    report = (tmp_path / "coverage.xml").read_text()
    assert 'filename="src/double.rs"' in report
    assert "setup.rs" not in report
    done = _sh(diff, tmp_path, diff_env)
    output = done.stdout + done.stderr
    assert done.returncode != 0, output
    assert "double.rs" in output, output

    with (tmp_path / "src/double.rs").open("a") as f:
        f.write("\n#[cfg(test)]\nmod tests;\n")
    (tmp_path / "src/double").mkdir()
    (tmp_path / "src/double/tests.rs").write_text(
        "use super::double;\n\n"
        "#[test]\nfn doubles() {\n    assert_eq!(double(2), 4);\n}\n"
    )
    git(tmp_path, "add", "src")
    git(tmp_path, "commit", "-m", "test(cli): Cover double", "--no-verify")
    assert _sh(coverage, tmp_path).returncode == 0
    report = (tmp_path / "coverage.xml").read_text()
    assert "tests.rs" not in report  # test modules aren't code to cover
    done = _sh(diff, tmp_path, diff_env)
    assert done.returncode == 0, done.stdout + done.stderr
    for step in ("format_check", "lint", "test"):
        command = principles["components"][0]["commands"][step]
        done = _sh(command, tmp_path)
        assert done.returncode == 0, f"{step}: {done.stdout}{done.stderr}"
    assert git(tmp_path, "status", "--porcelain") == ""


_SIDE = (
    "//! Sides of zero.\n\n"
    "/// Which side of zero `n` is on: -1 below it, 1 at or above it.\n"
    "#[must_use]\n"
    "pub fn side(n: i32) -> i32 {\n"
    "    if n < 0 { -1 } else { 1 }\n"
    "}\n\n"
    "#[cfg(test)]\nmod tests;\n"
)
_SIDE_BELOW = (
    "use super::side;\n\n#[test]\nfn below() {\n    assert_eq!(side(-1), -1);\n}\n"
)
_SIDE_AT = "\n#[test]\nfn at() {\n    assert_eq!(side(0), 1);\n}\n"


def _ci_steps(project: Path, job: str) -> dict[str, str]:
    """The pull-request steps of a component's CI job as local commands: the
    pinned diff-cover through `uvx`, and the base as a local branch."""
    workflow = yaml.safe_load((project / ".github/workflows/ci.yml").read_text())
    return {
        s["name"]: s["run"]
        .replace("pipx run", "uvx")
        .replace("origin/${BASE_REF}", "${BASE_REF}")
        for s in workflow["jobs"][job]["steps"]
        if "name" in s
    }


def _commit(project: Path, message: str, *paths: str) -> None:
    git(project, "add", *paths)
    git(project, "commit", "-m", message, "--no-verify")


def _add_side(crate: Path) -> None:
    """A module whose `if` only one test side reaches, on one line: every
    line runs, and the mutant `<` as `<=` survives."""
    (crate / "src/side").mkdir(parents=True)
    (crate / "src/lib.rs").write_text("//! Tidy.\n\npub mod side;\n")
    (crate / "src/side.rs").write_text(_SIDE)
    (crate / "src/side/tests.rs").write_text(_SIDE_BELOW)


@pytest.mark.slow
@NEEDS_CARGO
def test_exhaustive_gate_catches_a_half_tested_rust_branch(
    tmp_path: Path, git_env: None
):
    """Decision 0028: diff-cover reads the branches cargo-llvm-cov records
    on the recipe's nightly."""
    answers = place_answers(tmp_path, "rust-cli")
    data = json.loads(answers.read_text())
    data["testing"]["exhaustive"] = True
    answers.write_text(json.dumps(data))
    generate(tmp_path, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), 2026, TODAY)
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    commit_skeleton(tmp_path, principles, [])
    git(tmp_path, "branch", "-M", "main")
    git(tmp_path, "switch", "-c", "feature")
    steps = _ci_steps(tmp_path, "cli")
    coverage, diff = steps["test with coverage"], steps["diff coverage"]
    assert diff.endswith("--branch-coverage")
    env = {**os.environ, "BASE_REF": "main"}

    _add_side(tmp_path)
    _commit(tmp_path, "feat(cli): Add side", "src")
    done = _sh(coverage, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "condition-coverage" in (tmp_path / "coverage.xml").read_text()
    # Every line ran, so only the untaken side of the `if` fails the gate.
    lines_only = _sh(diff.removesuffix(" --branch-coverage"), tmp_path, env)
    assert lines_only.returncode == 0, lines_only.stdout + lines_only.stderr
    done = _sh(diff, tmp_path, env)
    output = done.stdout + done.stderr
    assert done.returncode != 0, output
    assert "side.rs" in output, output

    (tmp_path / "src/side/tests.rs").write_text(_SIDE_BELOW + _SIDE_AT)
    _commit(tmp_path, "test(cli): Cover both sides", "src")
    assert _sh(coverage, tmp_path).returncode == 0
    done = _sh(diff, tmp_path, env)
    assert done.returncode == 0, done.stdout + done.stderr
    for step in ("format_check", "lint", "test"):
        command = principles["components"][0]["commands"][step]
        done = _sh(command, tmp_path)
        assert done.returncode == 0, f"{step}: {done.stdout}{done.stderr}"
    assert git(tmp_path, "status", "--porcelain") == ""
