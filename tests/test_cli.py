import subprocess
import sys
from pathlib import Path

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
