"""Plain helpers shared by the generator tests (fixtures live in conftest.py)."""

import shutil
import subprocess
from datetime import date
from pathlib import Path

from alpha.cli import PLUGIN_ROOT

SCENARIOS = PLUGIN_ROOT / "evals" / "scenarios"
TODAY = date(2026, 10, 19)


def place_answers(target: Path, scenario: str) -> Path:
    dest = target / ".claude" / "alpha" / "project.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SCENARIOS / f"{scenario}.json", dest)
    return dest


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def old_python() -> str | None:
    """A python3 older than 3.11 on this machine (e.g. stock macOS), if any."""
    for candidate in ("/usr/bin/python3", "python3.9", "python3.10"):
        exe = shutil.which(candidate)
        if exe is None:
            continue
        done = subprocess.run(
            [exe, "-c", "import sys; print(sys.version_info[:2] < (3, 11))"],
            capture_output=True,
            text=True,
        )
        if done.returncode == 0 and done.stdout.strip() == "True":
            return exe
    return None
