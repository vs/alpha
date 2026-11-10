import json
import os
import shutil
import subprocess
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from helpers import TODAY, git, place_answers

from alpha import cli
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
    tmp_path: Path, scenario: str, generate_scenario, git_env
):
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
    tmp_path: Path, generate_scenario, git_env
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
def test_typescript_at_the_root_runs_green(tmp_path: Path, git_env):
    answers = place_answers(tmp_path, "python-ml-single")
    data = json.loads(answers.read_text())
    data["components"][0].update(stack="typescript", kind="cli")
    answers.write_text(json.dumps(data))
    generate(tmp_path, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), 2026, TODAY)
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)
    commit_skeleton(tmp_path, principles, [])
    assert git(tmp_path, "status", "--porcelain") == ""


@pytest.mark.slow
@NEEDS_CARGO
def test_rust_recipe_is_proven_by_try(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    answers = place_answers(tmp_path, "rust-cli")
    data = json.loads(answers.read_text())
    del data["recipes"]["rust"]["proven_hash"]
    answers.write_text(json.dumps(data))
    assert cli.main(["recipe", "try", str(tmp_path), "rust"]) == 0
    assert capsys.readouterr().out.strip() == "ok: rust recipe proven"


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
    tmp_path: Path, scenario: str, generate_scenario, git_env
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
def seeded(bootstrapped_web: Path, request: pytest.FixtureRequest) -> Iterator[Path]:
    """The bootstrapped project with one seed applied, reverted afterwards."""
    _, rel, change, _ = SEEDS[request.param]
    path = bootstrapped_web / rel
    before = path.read_text() if path.exists() else None
    after = change(before)
    assert after != before, f"the {request.param} seed changed nothing"
    path.write_text(after)
    try:
        yield bootstrapped_web
    finally:
        if before is None:
            path.unlink()
        else:
            path.write_text(before)


@pytest.mark.slow
@pytest.mark.parametrize("seeded", list(SEEDS), indirect=True)
def test_repo_checks_can_fail(seeded: Path, request: pytest.FixtureRequest):
    check = request.node.callspec.params["seeded"]
    pin = load_registry(Source(PLUGIN_ROOT, True)).tool(SEEDS[check][0]).pin
    assert pin is not None
    done = mise_run(seeded, f"check:{check}")
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
    tmp_path: Path, generate_scenario, git_env
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
def test_depcruise_reports_a_cycle(tmp_path: Path, generate_scenario, git_env):
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
def test_diff_cover_catches_untested_line(tmp_path: Path, generate_scenario, git_env):
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
    tmp_path: Path, generate_scenario, git_env
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
