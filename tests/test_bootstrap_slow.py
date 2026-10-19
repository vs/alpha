import subprocess
import tomllib
from pathlib import Path

import pytest

from alpha.generate import bootstrap
from alpha.gitops import commit_skeleton
from alpha.recipes import load_recipe


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


@pytest.mark.slow
@pytest.mark.parametrize("scenario", ["python-ml-single", "web-ts-plus-python-api"])
def test_bootstrap_runs_green(
    tmp_path: Path, scenario: str, generate_scenario, git_env
):
    generate_scenario(tmp_path, scenario)
    principles = tomllib.loads((tmp_path / "docs/principles.toml").read_text())
    bootstrap(tmp_path, principles)  # raises unless bootstrap, setup and test exit 0
    for c in principles["components"]:
        for lockfile in load_recipe(c["stack"]).lockfiles:
            assert (tmp_path / c["path"] / lockfile).is_file()

    commit_skeleton(tmp_path, principles, [])
    assert git(tmp_path, "status", "--porcelain") == ""
    tracked = git(tmp_path, "ls-files").splitlines()
    for c in principles["components"]:
        for lockfile in load_recipe(c["stack"]).lockfiles:
            prefix = "" if c["path"] == "." else f"{c['path']}/"
            assert f"{prefix}{lockfile}" in tracked
    junk = (".venv/", "__pycache__/", ".pytest_cache/", "node_modules/")
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
            assert done.returncode == 0, f"{command}: {done.stdout}{done.stderr}"
    assert git(tmp_path, "status", "--porcelain") == ""
