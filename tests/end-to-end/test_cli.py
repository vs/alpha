import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHIM = ROOT / "bin" / "alpha"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SHIM), *args], capture_output=True, text=True
    )


def test_version_via_shim():
    out = run("version")
    assert out.returncode == 0
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert out.stdout.strip() == plugin["version"] == project["version"]


def test_unknown_command_explains_usage():
    out = run("nope")
    assert out.returncode == 2
    assert "usage" in out.stderr.lower()


MIN_PYTHON = shutil.which("python3.11")


@pytest.mark.skipif(MIN_PYTHON is None, reason="needs python3.11, the minimum")
def test_every_module_imports_and_the_cli_runs_on_python_3_11():
    # The dev venv may run a newer Python whose lazy annotations hide names
    # used only under TYPE_CHECKING; users run alpha on 3.11 too.
    assert MIN_PYTHON is not None
    load_all = (
        "import importlib, pkgutil, alpha; "
        "[importlib.import_module(f'alpha.{m.name}') "
        "for m in pkgutil.walk_packages(alpha.__path__)]"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    done = subprocess.run(
        [MIN_PYTHON, "-c", load_all], capture_output=True, text=True, env=env
    )
    assert done.returncode == 0, done.stderr
    done = subprocess.run(
        [MIN_PYTHON, str(SHIM), "recipe", "list"],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    assert "python (proven)" in done.stdout


def test_startup_budget_bin_alpha_help_under_200_ms():
    """docs/performance.md: bin/alpha starts in under 200 ms. The best of five
    runs, so one slow scheduler tick on a busy machine doesn't fail it."""
    shim = ROOT / "bin" / "alpha"
    times: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        done = subprocess.run([str(shim), "--help"], capture_output=True, timeout=30)
        times.append(time.perf_counter() - started)
        assert done.returncode == 0, done.stderr
    assert min(times) < 0.2, f"bin/alpha --help took {min(times) * 1000:.0f} ms at best"
