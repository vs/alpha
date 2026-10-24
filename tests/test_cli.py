import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "bin" / "alpha"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SHIM), *args], capture_output=True, text=True
    )


def test_version_via_shim():
    out = run("version")
    assert out.returncode == 0
    assert out.stdout.strip() == "0.1.0"


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
