import json
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from alpha import pyguard

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


def min_python() -> str:
    """An interpreter of the Python version alpha supports at least: uv finds
    an installed one or downloads it once."""
    version = ".".join(str(n) for n in pyguard.MIN_PYTHON)
    done = subprocess.run(
        [
            "uv",
            "run",
            "--python",
            version,
            "--no-project",
            "python",
            "-c",
            "import sys; print(sys.executable)",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_every_module_imports_and_the_cli_runs_on_python_3_11():
    # The dev venv may run a newer Python whose lazy annotations hide names
    # used only under TYPE_CHECKING; users run alpha on 3.11 too.
    python = min_python()
    load_all = (
        "import importlib, pkgutil, alpha; "
        "[importlib.import_module(f'alpha.{m.name}') "
        "for m in pkgutil.walk_packages(alpha.__path__)]"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    done = subprocess.run(
        [python, "-c", load_all], capture_output=True, text=True, env=env
    )
    assert done.returncode == 0, done.stderr
    done = subprocess.run(
        [python, str(SHIM), "recipe", "list"],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    assert "python (proven)" in done.stdout


def test_startup_budget_bin_alpha_help_under_200_ms():
    """docs/alpha/specification.md, Performance: bin/alpha starts in under 200 ms.
    The best of five runs, so one slow scheduler tick on a busy machine
    doesn't fail it."""
    shim = ROOT / "bin" / "alpha"
    times: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        done = subprocess.run([str(shim), "--help"], capture_output=True, timeout=30)
        times.append(time.perf_counter() - started)
        assert done.returncode == 0, done.stderr
    assert min(times) < 0.2, f"bin/alpha --help took {min(times) * 1000:.0f} ms at best"
