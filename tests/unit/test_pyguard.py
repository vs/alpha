import ast
import subprocess
from pathlib import Path

import pytest
from helpers import old_python, union_annotations

from alpha.cli import PLUGIN_ROOT
from alpha.pyguard import check_python

# Everything the shim runs before the version check must work on Python 3.9.
GUARDED = [
    PLUGIN_ROOT / "bin" / "alpha",
    PLUGIN_ROOT / "src" / "alpha" / "__init__.py",
    PLUGIN_ROOT / "src" / "alpha" / "pyguard.py",
]


def test_old_python_gets_fix_hint():
    msg = check_python((3, 9))
    assert msg is not None
    assert "3.11+" in msg
    assert "found 3.9" in msg
    assert "uv python install" in msg


def test_new_python_passes():
    assert check_python((3, 11)) is None


@pytest.mark.parametrize("path", GUARDED, ids=lambda p: p.name)
def test_runs_before_the_guard_on_python_3_9(path: Path):
    tree = ast.parse(path.read_text(), str(path), feature_version=(3, 9))
    assert union_annotations(tree) == [], f"{path}: needs lazy annotations"


def test_shim_on_old_python_prints_the_guard_message():
    exe = old_python()
    if exe is None:
        pytest.skip("no python3 older than 3.11 on this machine")
    done = subprocess.run(
        [exe, str(PLUGIN_ROOT / "bin" / "alpha"), "version"],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 1
    assert "Traceback" not in done.stderr
    assert done.stderr.startswith("alpha needs Python 3.11+ (found 3.")
