"""Adopting a real repo end to end (spec §5b): survey facts aside, apply
alpha's files onto a uv service with legacy findings, merge the conflicts,
capture the baselines while bootstrapping green, commit, and check that the
app is untouched and alpha treats it as its own."""

import json
import os
import subprocess
from datetime import date
from pathlib import Path

import pytest
from helpers import PLUGIN_ROOT, adoption_answers, existing_repo, git

from alpha.adopt import apply_adoption, plan_adoption
from alpha.defaults import Source
from alpha.generate import bootstrap, load_project_principles
from alpha.gitops import PROPOSALS, commit_update
from alpha.update import describe, plan_update

SOURCE = Source(PLUGIN_ROOT, True)
TODAY = date(2026, 11, 11)
PYPROJECT = """\
[project]
name = "legacy"
version = "1.0"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = ["pytest", "ruff", "pyright", "deptry"]

[tool.uv]
package = false

[tool.pytest.ini_options]
pythonpath = ["src"]
"""
APP = {
    "pyproject.toml": PYPROJECT,
    "src/legacy/__init__.py": "",
    # ruff F401; pyright reportReturnType (and reportUnusedImport off in basic).
    "src/legacy/core.py": (
        "import os\n\n\ndef double(x: int) -> int:\n    return str(x)\n"
    ),
    "tests/test_core.py": (
        "from legacy.core import double\n\n\n"
        "def test_double() -> None:\n    assert double(2) == 4\n"
    ),
    "README.md": "# Legacy\n\nOur service. Run it with `uv run python -m legacy`.\n",
    "LICENSE": "Copyright the legacy authors. All rights reserved.\n",
    ".gitignore": ".venv/\n__pycache__/\n.pytest_cache/\n",
    "docs/decisions/0001-use-uv.md": "# 0001. Use uv\n\nStatus: accepted\n",
}
BASELINES = ["lint:ml", "typecheck:ml", "test:ml", "typos", "markdown"]


def _resolve(text: str) -> str:
    """Each conflict hunk as the repo's side, then alpha's: a mechanical
    stand-in for Claude's hand merge."""
    out: list[str] = []
    side = None
    ours: list[str] = []
    theirs: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("<<<<<<< "):
            side, ours, theirs = "ours", [], []
        elif line.startswith("||||||| ") and side:
            side = "base"
        elif line.startswith("=======") and side:
            side = "theirs"
        elif line.startswith(">>>>>>> ") and side:
            out += ours + (["\n"] if ours and theirs else []) + theirs
            side = None
        elif side == "ours":
            ours.append(line)
        elif side == "theirs":
            theirs.append(line)
        elif side is None:
            out.append(line)
    return "".join(out)


def _sh(cwd: Path, command: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "ALPHA_BASE")}
    return subprocess.run(
        command, shell=True, cwd=cwd, capture_output=True, text=True, env=env
    )


@pytest.mark.slow
def test_adopt_a_real_repo(tmp_path: Path, git_env: None):
    """R4: adopt apply and bootstrap --capture-baselines baseline legacy
    findings, and a new one fails."""
    root = tmp_path / "repo"
    root.mkdir()
    for rel, text in APP.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    assert _sh(root, "uv lock").returncode == 0
    existing_repo(root, {})  # git init and commit what's there
    app = {rel: (root / rel).read_bytes() for rel in [*APP, "uv.lock"]}
    start = git(root, "rev-parse", "HEAD")
    adoption_answers(root, baselines=BASELINES)

    plan = plan_adoption(root, PLUGIN_ROOT, SOURCE, TODAY)
    apply_adoption(root, plan)
    for c in plan.update.changes:
        if c.kind == "conflict":
            (root / c.path).write_text(
                _resolve((root / PROPOSALS / c.path).read_text())
            )
    bootstrap(root, load_project_principles(root), capture_baselines=True)
    commit_update(
        root, load_project_principles(root), ["Co-Authored-By: T <t@example.com>"]
    )

    assert git(root, "status", "--porcelain") == ""
    assert git(root, "rev-parse", "--abbrev-ref", "HEAD") == "alpha/adopt"
    for rel, data in app.items():  # the app, its manifest and lockfile: untouched
        if rel not in ("README.md", ".gitignore"):
            assert (root / rel).read_bytes() == data, rel
    changed = git(root, "diff", "--name-only", start, "HEAD").splitlines()
    assert not [p for p in changed if p.startswith(("src/", "tests/"))]
    assert "docs/decisions/0002-" in "\n".join(changed)
    counts = json.loads(
        (root / ".claude/alpha/baselines/typecheck.ml.json").read_text()
    )
    assert counts["counts"] == {"src/legacy/core.py": {"reportReturnType": 1}}

    assert _sh(root, "mise run --continue-on-error ci").returncode == 0
    core = root / "src/legacy/core.py"
    core.write_text(
        APP["src/legacy/core.py"] + "\n\ndef half(x: int) -> int:\n    return str(x)\n"
    )
    done = _sh(root, "mise run check:component:ml")
    assert done.returncode != 0
    assert "reportReturnType: 2 now, 1 in the baseline" in done.stdout + done.stderr
    core.write_text(APP["src/legacy/core.py"])

    update = plan_update(root, SOURCE, TODAY)
    assert describe(update, root) == "alpha update: nothing to change"
