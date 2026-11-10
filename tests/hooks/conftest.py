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

sys.path.insert(0, str(HOOKS))


STUB = 'python3 -c "import sys; sys.exit(0)"'
OLD_PYTHON = [
    sys.executable,
    "-c",
    "import runpy, sys; sys.version_info = (3, 9, 6, 'final', 0); "
    "sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')",
]


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
        data = self.principles()
        known = [c["name"] for c in data["components"]]
        if component not in known:
            raise KeyError(f"unknown component {component!r}; known: {known}")
        for comp in data["components"]:
            if comp["name"] == component:
                comp["commands"].update(commands)
        self.write_principles(data)

    def drop_principle(self, principle: str, component: str | None = None) -> None:
        data = self.principles()
        found = [p for p in data["principles"] if p["id"] == principle]
        if not found:
            raise KeyError(f"unknown principle {principle!r}")
        for p in found:
            if component is None:
                p["active"] = False
            else:
                p["components"] = [n for n in p["components"] if n != component]
        self.write_principles(data)

    def run_hook(
        self,
        script: str,
        payload: dict[str, Any],
        cwd: Path | None = None,
        env: dict[str, str | None] | None = None,
        python: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        full: dict[str, str] = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root)}
        for key, value in (env or {}).items():
            if value is None:
                full.pop(key, None)
            else:
                full[key] = value
        return subprocess.run(
            [*(python or [sys.executable]), str(HOOKS / script)],
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
    for comp in data["components"]:
        comp["commands"] = dict.fromkeys(comp["commands"], STUB)
    for check in data.get("repo_checks", []):  # nor the real repository checks
        check["stop"] = False
    p.write_principles(data)
    return p


@pytest.fixture(autouse=True)
def isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Keep hook subprocesses off the real ~/.cache/alpha/slots.

    Git keeps the user's global config (or the test's own GIT_CONFIG_GLOBAL).
    """
    real = Path.home() / ".gitconfig"
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    if "GIT_CONFIG_GLOBAL" not in os.environ and real.is_file():
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(real))
    return home
