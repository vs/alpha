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
