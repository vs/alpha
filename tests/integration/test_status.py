"""alpha status: the state /alpha:install reads (rewrite spec, R1.2 and R1.5)."""

import json
from pathlib import Path

from helpers import (
    adoption_answers,
    existing_repo,
    generated_repo,
    git,
    place_answers,
    run_cli,
)

from alpha.status import status


def name(target: Path) -> str:
    return status(target).name


def test_R1_2_each_folder_state_is_told_apart(tmp_path: Path, git_env: None):
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / ".DS_Store").write_text("")
    assert name(empty) == "empty"
    unborn = tmp_path / "unborn"
    unborn.mkdir()
    git(unborn, "init", "-q")
    assert name(unborn) == "empty"
    (unborn / "notes.md").write_text("x\n")
    assert name(unborn) == "uncommitted"
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "main.py").write_text("print(1)\n")
    assert name(loose) == "not-a-repo"
    repo = existing_repo(tmp_path / "repo")
    assert name(repo) == "existing"
    (repo / "newsvc").mkdir()  # a new project's folder inside another repo
    assert name(repo / "newsvc") == "empty"
    (repo / "README.md").write_text("edited\n")
    assert name(repo) == "uncommitted"
    git(repo, "checkout", "--", "README.md")
    git(repo, "branch", "alpha/adopt")
    assert name(repo) == "adopting"
    interview = tmp_path / "interview"
    place_answers(interview, "python-ml-single")
    assert name(interview) == "interview"
    installed = generated_repo(tmp_path / "installed", "python-ml-single")
    assert name(installed) == "installed"
    git(installed, "config", "--unset", "core.hooksPath")
    off = status(installed)
    assert off.name == "hooks-off" and "core.hooksPath" in off.detail
    old = tmp_path / "old"
    path = place_answers(old, "python-ml-single")
    data = json.loads(path.read_text())
    data["manifest"] = {"kit_version": "0.8.0"}
    path.write_text(json.dumps(data))
    assert name(old) == "old-kit"
    out = run_cli("status", str(loose))
    assert out.returncode == 0
    assert out.stdout.startswith("not-a-repo: run git init")


def test_R1_5_an_adopted_repo_names_its_next_step(tmp_path: Path, git_env: None):
    repo = existing_repo(tmp_path / "repo")
    step = {
        "id": "p2-lint-ml",
        "phase": "P2",
        "title": "Add a linter",
        "why": "Nothing lints it.",
        "acceptance": [{"run": "true"}],
        "status": "pending",
    }
    data = adoption_answers(repo, steps=[step])
    data["installed"] = {"kit_version": "1.0.0", "mode": "adopted"}
    (repo / ".claude/alpha/project.json").write_text(json.dumps(data))
    git(repo, "config", "core.hooksPath", ".claude/alpha/githooks")
    settings = repo / ".claude/settings.json"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 .claude/alpha/hooks/stop.py",
                                }
                            ]
                        }
                    ]
                }
            }
        )
    )
    found = status(repo)
    assert found.name == "installed"
    assert "p2-lint-ml" in found.detail
