"""A purged project still builds and tests, on real toolchains (rewrite spec,
R3.3): uv, pnpm and mise, with network access."""

import subprocess
import tomllib
from pathlib import Path

import pytest
from helpers import git, place_answers, run_cli


def mise_run(cwd: Path, task: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["mise", "run", task], cwd=cwd, capture_output=True, text=True
    )


@pytest.mark.slow
def test_R3_3_a_purged_project_builds_and_tests(tmp_path: Path, git_env: None) -> None:
    target = tmp_path / "app"
    place_answers(target, "web-ts-plus-python-api")
    for step in ("apply", "bootstrap", "commit"):
        done = run_cli(step, str(target))
        assert done.returncode == 0, f"alpha {step}: {done.stdout}{done.stderr}"
    principles = tomllib.loads((target / "docs/alpha/principles.toml").read_text())
    names = [c["name"] for c in principles["components"]]
    done = run_cli("purge", str(target))
    assert done.returncode == 0, done.stdout + done.stderr
    assert not (target / ".claude/alpha").exists()
    assert git(target, "status", "--porcelain") == ""
    for name in names:
        done = mise_run(target, f"check:component:{name}")
        assert done.returncode == 0, done.stdout + done.stderr
    done = mise_run(target, "ci")
    assert done.returncode == 0, done.stdout + done.stderr
    assert git(target, "status", "--porcelain") == ""
