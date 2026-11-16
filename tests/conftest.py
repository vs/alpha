from pathlib import Path

import pytest
from helpers import GenerateScenario, install, place_answers


@pytest.fixture(autouse=True)
def own_alpha_config(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ALPHA_CONFIG_DIR", str(tmp_path_factory.mktemp("alpha")))
    monkeypatch.delenv("ALPHA_SOURCE", raising=False)
    # CI sets CI=true, which freezes baselines and skips the hooks' slots; a
    # test that needs it sets it itself.
    monkeypatch.delenv("CI", raising=False)


@pytest.fixture
def generate_scenario() -> GenerateScenario:

    def run(target: Path, scenario: str) -> list[str]:
        place_answers(target, scenario)
        return install(target)

    return run


@pytest.fixture
def git_env(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path_factory.mktemp("gitconfig") / "config"
    # git packs objects in a detached process after a commit, which deletes
    # files under .git while a test copies or snapshots the repository.
    config.write_text("[maintenance]\n\tauto = false\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")
