"""install on an empty folder, on real toolchains (rewrite spec, R1.1 and
R12.2): uv, pnpm and mise, with network access."""

import subprocess
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
from helpers import REPO_SEEDS as SEEDS
from helpers import git, install, place_answers, run_cli

from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import bootstrap
from alpha.registry import load_registry

SCENARIO = "web-ts-plus-python-api"


def mise_run(cwd: Path, task: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["mise", "run", task], cwd=cwd, capture_output=True, text=True
    )


@pytest.mark.slow
def test_R1_1_empty_folder_becomes_a_checked_project(
    tmp_path: Path, git_env: None
) -> None:
    target = tmp_path / "app"
    place_answers(target, SCENARIO)
    for step in ("apply", "bootstrap", "commit"):
        done = run_cli(step, str(target))
        assert done.returncode == 0, f"alpha {step}: {done.stdout}{done.stderr}"
    assert git(target, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git(target, "status", "--porcelain") == ""
    principles = tomllib.loads((target / "docs/alpha/principles.toml").read_text())
    for component in principles["components"]:
        done = mise_run(target, f"check:component:{component['name']}")
        assert done.returncode == 0, done.stdout + done.stderr
    done = mise_run(target, "ci")
    assert done.returncode == 0, done.stdout + done.stderr
    assert git(target, "status", "--porcelain") == ""
    tracked = git(target, "ls-files").splitlines()
    sources = [p for p in tracked if p.startswith(("api/src/", "web/src/"))]
    assert sources == [], "no app code"


@pytest.fixture(scope="module")
def bootstrapped_web(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("web")
    place_answers(target, SCENARIO)
    install(target)
    bootstrap(
        target, tomllib.loads((target / "docs/alpha/principles.toml").read_text())
    )
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
def test_R12_2_each_check_fails_on_its_seed(seeded: tuple[str, Path]) -> None:
    check, project = seeded
    pin = load_registry(Source(PLUGIN_ROOT, True)).tool(SEEDS[check][0]).pin
    assert pin is not None
    done = mise_run(project, f"check:{check}")
    output = done.stdout + done.stderr
    # mise run passes the task's exit code through unchanged.
    assert done.returncode == pin.fails_with, output
    assert SEEDS[check][3] in output, output
