import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from alpha.answers import load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles, render_principles

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / "project-files" / "hooks"
FIXTURE = REPO / "tests" / "fixtures" / "answers_valid.json"

# Hooks import each other as plain modules; tests import them the same way.
sys.path.insert(0, str(HOOKS))


STUB = 'python3 -c "import sys; sys.exit(0)"'


class Project:
    def __init__(self, root: Path) -> None:
        self.root = root

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True, check=True
        )

    def write(self, rel: str, text: str = "") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def principles(self) -> dict[str, Any]:
        with (self.root / "docs" / "principles.toml").open("rb") as f:
            return tomllib.load(f)

    def write_principles(self, data: dict[str, Any]) -> None:
        self.write("docs/principles.toml", render_principles(data))

    def set_commands(self, component: str, **commands: str) -> None:
        """Override a component's commands, e.g. test="python3 -c ..."."""
        data = self.principles()
        known = [c["name"] for c in data["components"]]
        if component not in known:
            raise KeyError(f"unknown component {component!r}; known: {known}")
        for comp in data["components"]:
            if comp["name"] == component:
                comp["commands"].update(commands)
        self.write_principles(data)

    def run_hook(
        self,
        script: str,
        payload: dict[str, Any],
        cwd: Path | None = None,
        env: dict[str, str | None] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a hook; env values override, and a None value removes the variable."""
        full: dict[str, str] = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        for key, value in (env or {}).items():
            if value is None:
                full.pop(key, None)
            else:
                full[key] = value
        return subprocess.run(
            [sys.executable, str(HOOKS / script)],
            cwd=cwd or self.root,
            env=full,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )


@pytest.fixture
def project(tmp_path: Path) -> Project:
    p = Project(tmp_path)
    p.git("init", "-q")
    p.git("config", "user.name", "Test")
    p.git("config", "user.email", "test@example.com")
    defaults = load_defaults(Source(PLUGIN_ROOT, True, ""))
    data = build_principles(defaults, load_answers(FIXTURE), "0.1.0")
    for comp in data["components"]:  # never let a hook test run real tooling
        comp["commands"] = dict.fromkeys(comp["commands"], STUB)
    p.write_principles(data)
    return p
