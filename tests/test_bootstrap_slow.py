import json
import subprocess
import tomllib
from pathlib import Path

import pytest
from helpers import TODAY, git, place_answers

from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import bootstrap, generate
from alpha.gitops import commit_skeleton
from alpha.recipes import load_recipe


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
