"""alpha baseline show, capture and tighten, and bootstrap's capture (spec
§8b), on a project whose check is a fake tool."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from helpers import PLUGIN_ROOT, git, run_cli, shell_recipe

from alpha.generate import GenerateError, bootstrap
from alpha.principles import render_principles

FAKE = """\
import pathlib, sys
found = 0
for path in sorted(pathlib.Path(sys.argv[1]).rglob("*.py")):
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if "BAD" in line:
            print(f"{path.as_posix()}:{n}: E1 bad")
            found += 1
sys.exit(1 if found else 0)
"""
PATTERN = r"^(?P<file>[^:\s]+):\d+: (?P<rule>E\d+)"
CHECK = "lint:api"
BASELINE = ".claude/alpha/baselines/lint.api.json"
RECORD = "# {n:04d}. Keep a finding\n\nDate: 2026-11-11\nStatus: {status}\n\n{body}\n"


def _project(tmp_path: Path, components: list[dict[str, Any]] | None = None) -> Path:
    root = tmp_path / "proj"
    for name, folder in (("ratchet.py", "checks"), ("_common.py", "hooks")):
        src = PLUGIN_ROOT / "project-files" / folder / name
        dest = root / ".claude" / "alpha" / folder / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)
    (root / "bin").mkdir()
    (root / "bin" / "fake.py").write_text(FAKE)
    (root / "api" / "src").mkdir(parents=True)
    (root / "api" / "src" / "app.py").write_text("a = 'BAD'\nb = 'BAD'\n")
    (root / "docs" / "decisions").mkdir(parents=True)
    entry = {
        "id": CHECK,
        "dir": "api",
        "command": "python3 ../bin/fake.py src",
        "pattern": PATTERN,
    }
    principles = {"components": components or [], "baselines": [entry]}
    (root / "docs" / "principles.toml").write_text(render_principles(principles))
    git(root, "init", "-q", "-b", "main")
    return root


def _counts(root: Path) -> dict[str, dict[str, int]]:
    return json.loads((root / BASELINE).read_text())["counts"]


def test_show_before_and_after_capture(tmp_path: Path):
    root = _project(tmp_path)
    shown = run_cli("baseline", "show", str(root))
    assert shown.returncode == 0
    assert f"{CHECK}: not captured. Run alpha baseline capture" in shown.stdout
    assert run_cli("baseline", "capture", str(root), "--all").returncode == 0
    shown = run_cli("baseline", "show", str(root), "--json")
    [row] = json.loads(shown.stdout)
    assert row == {
        "check": CHECK,
        "captured": True,
        "total": 2,
        "files": 1,
        "rules": {"E1": 2},
    }


def test_capture_all_creates_missing_only(tmp_path: Path):
    root = _project(tmp_path)
    (root / BASELINE).parent.mkdir(parents=True)
    (root / BASELINE).write_text(json.dumps({"check": CHECK, "counts": {}}))
    done = run_cli("baseline", "capture", str(root), "--all")
    assert done.returncode == 0
    assert "Every baselined check is captured." in done.stdout
    assert _counts(root) == {}


def test_capture_growth_needs_decision(tmp_path: Path):
    root = _project(tmp_path)
    assert run_cli("baseline", "capture", str(root), "--check", CHECK).returncode == 0
    (root / "api" / "src" / "app.py").write_text("a = 'BAD'\nb = 'BAD'\nc = 'BAD'\n")
    done = run_cli("baseline", "capture", str(root), "--check", CHECK)
    assert done.returncode == 1
    assert "would grow its baseline" in done.stderr
    assert "api/src/app.py E1: 3 now, 2 in the baseline" in done.stderr
    assert _counts(root) == {"api/src/app.py": {"E1": 2}}  # left as it was
    record = root / "docs" / "decisions" / "0007-keep-a-finding.md"
    record.write_text(RECORD.format(n=7, status="accepted", body="No check named."))
    done = run_cli(
        "baseline", "capture", str(root), "--check", CHECK, "--decision", "7"
    )
    assert done.returncode == 1 and f"`{CHECK}`" in done.stderr
    assert _counts(root) == {"api/src/app.py": {"E1": 2}}
    record.write_text(RECORD.format(n=7, status="accepted", body=f"`{CHECK}` grows."))
    done = run_cli(
        "baseline", "capture", str(root), "--check", CHECK, "--decision", "7"
    )
    assert done.returncode == 0, done.stderr
    assert _counts(root) == {"api/src/app.py": {"E1": 3}}


def test_capture_names_a_missing_record(tmp_path: Path):
    root = _project(tmp_path)
    run_cli("baseline", "capture", str(root), "--check", CHECK)
    (root / "api" / "src" / "app.py").write_text("x = 'BAD'\n" * 3)
    done = run_cli(
        "baseline", "capture", str(root), "--check", CHECK, "--decision", "12"
    )
    assert done.returncode == 1 and "No decision record 12" in done.stderr


def test_capture_unknown_check(tmp_path: Path):
    root = _project(tmp_path)
    done = run_cli("baseline", "capture", str(root), "--check", "typos")
    assert done.returncode == 1 and f"baselined: {CHECK}" in done.stderr


def test_tighten_reports_changed(tmp_path: Path):
    root = _project(tmp_path)
    run_cli("baseline", "capture", str(root), "--all")
    done = run_cli("baseline", "tighten", str(root))
    assert done.returncode == 0
    assert "Every baseline already matches" in done.stdout
    (root / "api" / "src" / "app.py").write_text("a = 'BAD'\n")
    done = run_cli("baseline", "tighten", str(root), env={"CI": "true"})
    assert done.returncode == 0, done.stderr  # tightening never runs frozen
    assert f"tightened: {BASELINE} (commit it)" in done.stdout
    assert _counts(root) == {"api/src/app.py": {"E1": 1}}


def test_tighten_reports_a_new_finding(tmp_path: Path):
    root = _project(tmp_path)
    run_cli("baseline", "capture", str(root), "--all")
    (root / "api" / "src" / "app.py").write_text("x = 'BAD'\n" * 3)
    done = run_cli("baseline", "tighten", str(root))
    assert done.returncode == 1 and "3 now, 2 in the baseline" in done.stderr


def _component(setup: str) -> dict[str, Any]:
    ratchet = f"python3 ../.claude/alpha/checks/ratchet.py {CHECK}"
    return {
        "name": "api",
        "path": "api",
        "stack": "shell",
        "commands": {"setup": setup, "lint": ratchet, "test": "true"},
    }


def _with_recipe(root: Path) -> None:
    path = root / ".claude" / "alpha" / "project.json"
    path.write_text(json.dumps({"recipes": {"shell": shell_recipe()}}))


def test_bootstrap_names_a_missing_baseline(tmp_path: Path):
    root = _project(tmp_path, [_component("touch ../setup.marker")])
    _with_recipe(root)
    principles: dict[str, Any] = json.loads(json.dumps(_principles(root)))
    with pytest.raises(GenerateError, match="--capture-baselines") as e:
        bootstrap(root, principles)
    assert CHECK in str(e.value)
    assert not (root / "setup.marker").exists()  # stopped before any step


def test_bootstrap_captures_after_setup(tmp_path: Path):
    # The fake tool fails unless setup ran first: capture needs the toolchain.
    root = _project(tmp_path, [_component("touch ../setup.marker")])
    _with_recipe(root)
    data = _principles(root)
    data["baselines"][0]["command"] = (
        "test -f ../setup.marker && python3 ../bin/fake.py src"
    )
    (root / "docs" / "principles.toml").write_text(render_principles(data))
    bootstrap(root, data, capture_baselines=True)
    assert _counts(root) == {"api/src/app.py": {"E1": 2}}


def _principles(root: Path) -> dict[str, Any]:
    import tomllib

    return tomllib.loads((root / "docs" / "principles.toml").read_text())


def test_capture_needs_a_decision_new_to_the_branch(tmp_path: Path, git_env: None):
    root = _project(tmp_path)
    run_cli("baseline", "capture", str(root), "--check", CHECK)
    record = root / "docs" / "decisions" / "0007-keep-a-finding.md"
    record.write_text(RECORD.format(n=7, status="accepted", body=f"`{CHECK}` grows."))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: Start")
    git(root, "switch", "-q", "-c", "feature")
    (root / "api" / "src" / "app.py").write_text("x = 'BAD'\n" * 3)
    done = run_cli(
        "baseline", "capture", str(root), "--check", CHECK, "--decision", "7"
    )
    assert done.returncode == 1 and "already named `lint:api`" in done.stderr
