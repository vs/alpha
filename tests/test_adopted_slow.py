"""An adopted recipe on a real repo (spec §5b, A1): survey it, then prove a
recipe that runs its own mypy, black and pytest on its legacy code."""

import json
import subprocess
from pathlib import Path

import pytest
from helpers import git, run_cli

PYPROJECT = """\
[project]
name = "svc"
version = "0"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = ["mypy", "black", "pytest"]

[tool.uv]
package = false
"""
CORE = "def double(x: int) -> int:\n    return str(x)\n"
TESTS = """\
from app.core import double


def test_double() -> None:
    assert double(2) == "2"


def test_legacy() -> None:
    assert double(2) == 4
"""
# mypy's line format: "app/core.py:2: error: Incompatible ... [return-value]"
MYPY = r"^(?P<file>[^:\s]+):\d+: error: .*\[(?P<rule>[a-z-]+)\]$"


@pytest.mark.slow
def test_adopted_recipe_proves_on_a_real_repo(tmp_path: Path, git_env: None):
    root = tmp_path / "repo"
    files = {
        "svc/pyproject.toml": PYPROJECT,
        "svc/app/__init__.py": "",
        "svc/app/core.py": CORE,
        "svc/tests/test_core.py": TESTS,
        "svc/tests/__init__.py": "",
        "svc/.gitignore": ".venv/\n.mypy_cache/\n.pytest_cache/\n__pycache__/\n",
        ".github/workflows/ci.yml": "on: push\njobs: {}\n",
        "README.md": "# svc\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    lock = subprocess.run(
        ["uv", "lock"], cwd=root / "svc", capture_output=True, text=True
    )
    assert lock.returncode == 0, lock.stderr
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "feat: Start the service")

    surveyed = run_cli("adopt", "survey", str(root))
    assert surveyed.returncode == 0, surveyed.stderr
    found = json.loads(surveyed.stdout)
    [svc] = [c for c in found["components"] if c["path"] == "svc"]
    assert (svc["stack"], svc["sources"], svc["tests"]) == ("python", 2, 2)
    assert found["files"]["ci"] == [".github/workflows/ci.yml"]

    recipe = {
        "adopted": True,
        "extends": "python",
        "commands": {
            "lint": "",
            "lint_file": "",
            "format": "uv run black .",
            "format_check": "uv run black --check .",
            "format_file": "uv run black {file}",
            "typecheck": "uv run mypy --strict .",
            "structure": "",
        },
        "baseline": {
            "typecheck": {"command": "uv run mypy --strict .", "pattern": MYPY}
        },
    }
    components = [{"name": "svc", "path": "svc", "stack": "svc-python"}]
    saved = run_cli(
        "answers",
        "write",
        str(root),
        "--json",
        json.dumps({"components": components, "recipes": {"svc-python": recipe}}),
    )
    assert saved.returncode == 0, saved.stderr

    done = run_cli("recipe", "try", str(root), "svc-python")
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.startswith("ok: svc-python recipe proven on svc at ")
    # core.py's return-value, and the test's strict comparison-overlap.
    assert "svc: typecheck: 2 findings in 2 files (to baseline)" in done.stdout
    assert "svc: test: 1 findings in 1 files (to baseline)" in done.stdout
    assert len(git(root, "worktree", "list").splitlines()) == 1
    # Only alpha's answers are new; the repo itself is untouched.
    assert git(root, "status", "--porcelain") == "?? .claude/"
