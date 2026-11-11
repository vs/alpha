"""The hooks on a project with baselines (spec §8b): legacy findings don't
block, new ones do, and Claude can't edit a baseline."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from .conftest import HOOKS, Project

CHECKS = HOOKS.parent / "checks"
# Reports E1 for each line holding BAD, in the files or folders it's given.
FAKE = """\
import pathlib, sys
found = 0
for arg in sys.argv[1:]:
    root = pathlib.Path(arg)
    for path in sorted(root.rglob("*.py")) if root.is_dir() else [root]:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if "BAD" in line:
                print(f"{path.as_posix()}:{n}: E1 bad")
                found += 1
sys.exit(1 if found else 0)
"""
PATTERN = r"^(?P<file>[^:\s]+):\d+: (?P<rule>E\d+)"
TOOL = "python3 ../bin/fake.py"


@pytest.fixture
def baselined(project: Project) -> Project:
    for script, folder in (("ratchet.py", "checks"), ("_common.py", "hooks")):
        src = (CHECKS if folder == "checks" else HOOKS) / script
        dest = project.root / ".claude" / "alpha" / folder / script
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)
    project.write("bin/fake.py", FAKE)
    data = project.principles()
    ratchet = "python3 ../.claude/alpha/checks/ratchet.py"
    for comp in data["components"]:
        if comp["name"] == "api":
            comp["commands"]["lint_file"] = f"{ratchet} lint:api --file {{file}}"
            comp["commands"]["typecheck"] = f"{ratchet} typecheck:api"
    data["baselines"] = [
        {
            "id": "lint:api",
            "dir": "api",
            "command": f"{TOOL} src",
            "file_command": f"{TOOL} {{file}}",
            "pattern": PATTERN,
        },
        {
            "id": "typecheck:api",
            "dir": "api",
            "command": f"{TOOL} src",
            "pattern": PATTERN,
        },
    ]
    data["protected"]["paths"].append(".claude/alpha/baselines/**")
    project.write_principles(data)
    project.write("api/src/app.py", "ok = 1\nlegacy = 'BAD'\n")
    for check in ("lint.api", "typecheck.api"):
        counts = {"api/src/app.py": {"E1": 1}}
        project.write(
            f".claude/alpha/baselines/{check}.json",
            json.dumps({"check": check.replace(".", ":"), "counts": counts}),
        )
    project.git("add", "-A")
    project.git("commit", "-q", "-m", "chore: Baseline")
    return project


def post_edit(project: Project, rel: str) -> subprocess.CompletedProcess[str]:
    payload: dict[str, Any] = {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(project.root / rel)},
        "tool_response": {},
    }
    return project.run_hook("post_edit.py", payload)


def test_post_edit_allows_legacy_findings(baselined: Project):
    baselined.write("api/src/app.py", "ok = 2\nlegacy = 'BAD'\n")
    proc = post_edit(baselined, "api/src/app.py")
    assert proc.returncode == 0, proc.stderr


def test_post_edit_blocks_a_new_finding(baselined: Project):
    baselined.write("api/src/app.py", "new = 'BAD'\nlegacy = 'BAD'\n")
    proc = post_edit(baselined, "api/src/app.py")
    assert proc.returncode == 2
    assert "api/src/app.py E1: 2 now, 1 in the baseline" in proc.stderr
    assert "src/app.py:1: E1 bad" in proc.stderr


def _stop(project: Project) -> subprocess.CompletedProcess[str]:
    import review

    state = review.ensure_state(project.root)
    state["reviewed_tree"] = review.snapshot(project.root)
    review.save_state(project.root, state)
    payload = {"hook_event_name": "Stop", "stop_hook_active": False}
    return project.run_hook("stop_checks.py", payload)


def test_stop_typecheck_through_ratchet(baselined: Project):
    baselined.write("api/src/app.py", "ok = 3\nlegacy = 'BAD'\n")
    baselined.write("api/tests/test_app.py", "def test_x(): pass\n")
    proc = _stop(baselined)
    assert "typecheck" not in proc.stdout, proc.stdout
    baselined.write("api/src/app.py", "x = 'BAD'\nlegacy = 'BAD'\n")
    proc = _stop(baselined)
    reason = json.loads(proc.stdout)["reason"]
    assert "api: typecheck failed" in reason
    assert "E1: 2 now, 1 in the baseline" in reason


def test_baseline_edit_is_blocked(baselined: Project):
    path = baselined.root / ".claude/alpha/baselines/typecheck.api.json"
    proc = baselined.run_hook(
        "guard_paths.py", {"tool_name": "Write", "tool_input": {"file_path": str(path)}}
    )
    assert proc.returncode == 2
    assert "shrink by themselves" in proc.stderr
    assert "alpha baseline capture" in proc.stderr
    assert "Secrets belong" not in proc.stderr


def test_a_fixed_legacy_finding_tightens_the_baseline(baselined: Project):
    baselined.write("api/src/app.py", "ok = 4\n")
    assert post_edit(baselined, "api/src/app.py").returncode == 0
    path = Path(baselined.root / ".claude/alpha/baselines/lint.api.json")
    assert json.loads(path.read_text())["counts"] == {}


def test_stop_cache_follows_the_baseline(baselined: Project):
    baselined.write("api/src/app.py", "x = 'BAD'\nlegacy = 'BAD'\n")
    baselined.write("api/tests/test_app.py", "def test_x(): pass\n")
    assert "typecheck failed" in json.loads(_stop(baselined).stdout)["reason"]
    # The finding is accepted (alpha baseline capture), and only the baseline
    # changes: the cached block must not stand.
    baselined.write(
        ".claude/alpha/baselines/typecheck.api.json",
        json.dumps({"check": "typecheck:api", "counts": {"api/src/app.py": {"E1": 2}}}),
    )
    assert "typecheck" not in _stop(baselined).stdout
