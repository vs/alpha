import json
import re
import secrets
import shutil
import subprocess
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from helpers import TODAY, git, place_answers

from alpha import cli
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import bootstrap, generate, project_book
from alpha.gitops import commit_skeleton
from alpha.registry import load_registry

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
    bootstrap(tmp_path, principles)  # raises unless bootstrap, setup and test exit 0
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

    # The fresh skeleton passes its own checks, and formatting changes nothing.
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
    # A root component's checks see everything at the root: .claude/, docs/
    # and the CI workflow must all pass its formatter and linter.
    answers = place_answers(tmp_path, "python-ml-single")
    data = json.loads(answers.read_text())
    data["components"][0].update(stack="typescript", kind="cli")
    answers.write_text(json.dumps(data))
    generate(tmp_path, PLUGIN_ROOT, Source(PLUGIN_ROOT, True, ""), 2026, TODAY)
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)  # runs format_check, lint, typecheck and test
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


def _aws_key_pair(_: str | None) -> str:
    # Random, so the scanner can't skip it as a well-known example key.
    key_id = "AKIA" + "".join(
        secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(16)
    )
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/+"
    secret = "".join(secrets.choice(alphabet) for _ in range(40))
    return f"# Deploy\n\nAWS_ACCESS_KEY_ID={key_id}\nAWS_SECRET_ACCESS_KEY={secret}\n"


def _append(extra: str) -> Callable[[str | None], str]:
    return lambda text: (text or "") + extra


# check id -> (registry tool, the file it changes, how it changes it)
SEEDS: dict[str, tuple[str, str, Callable[[str | None], str]]] = {
    "actions": (
        "jactionlint",
        ".github/workflows/ci.yml",
        lambda text: re.sub(r"@[0-9a-f]{40}", "@v7", text or "", count=1),
    ),
    "secrets": ("betterleaks", "docs/x.md", _aws_key_pair),
    "typos": ("typos", "README.md", _append("\nteh\n")),
    "markdown": (
        "rumdl",
        "docs/x.md",
        lambda _: "# Notes\n\n### Skips a level\n\nText.\n",
    ),
    "links": ("lychee", "README.md", _append("\nSee [notes](docs/missing.md).\n")),
    "agent-config": (
        "agnix",
        ".claude/agents/committer.md",
        lambda text: (text or "").replace("model: inherit\n", "model: [inherit\n", 1),
    ),
}


@pytest.fixture(scope="module")
def bootstrapped_web(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("web")
    place_answers(target, "web-ts-plus-python-api")
    generate(target, PLUGIN_ROOT, Source(PLUGIN_ROOT, True, ""), 2026, TODAY)
    bootstrap(target, tomllib.loads((target / "docs/principles.toml").read_text()))
    return target


@pytest.fixture
def seeded(bootstrapped_web: Path, request: pytest.FixtureRequest) -> Iterator[Path]:
    """The bootstrapped project with one seed applied, reverted afterwards."""
    _, rel, change = SEEDS[request.param]
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
    pin = load_registry(Source(PLUGIN_ROOT, True, "")).tool(SEEDS[check][0]).pin
    assert pin is not None
    done = mise_run(seeded, f"check:{check}")
    # mise run passes the task's exit code through unchanged.
    assert done.returncode == pin.fails_with, done.stdout + done.stderr
