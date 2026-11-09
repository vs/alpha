from collections.abc import Callable
from pathlib import Path

import pytest
from helpers import TODAY, place_answers

from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import generate

GenerateScenario = Callable[[Path, str], list[str]]


@pytest.fixture
def generate_scenario() -> GenerateScenario:

    def run(target: Path, scenario: str) -> list[str]:
        place_answers(target, scenario)
        return generate(target, PLUGIN_ROOT, Source(PLUGIN_ROOT, True, ""), 2026, TODAY)

    return run


@pytest.fixture
def git_env(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    config = tmp_path_factory.mktemp("gitconfig") / "config"
    config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")
