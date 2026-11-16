"""alpha status: the state /alpha:install reads (spec, R1.2 and R1.5)."""

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


def plan_step(sid: str, phase: str, **more: object) -> dict[str, object]:
    return {
        "id": sid,
        "phase": phase,
        "title": "A step",
        "why": "Why it matters.",
        "acceptance": [{"run": "true"}],
        "status": "pending",
        **more,
    }


def installed_with(repo: Path, steps: list[dict[str, object]]) -> None:
    """repo, adopted with alpha's hooks on and this plan."""
    data = adoption_answers(repo, steps=steps)
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


def test_R1_5_an_adopted_repo_names_its_next_step(tmp_path: Path, git_env: None):
    repo = existing_repo(tmp_path / "repo")
    installed_with(repo, [plan_step("p2-lint-ml", "P2")])
    found = status(repo)
    assert found.name == "installed"
    assert "p2-lint-ml" in found.detail


def test_status_names_the_step_adopt_next_names(tmp_path: Path, git_env: None):
    """Listed P6 first, the P2 step comes first by phase; a step waiting on an
    unfinished one isn't ready. /alpha:install reads status, so it must agree
    with alpha adopt next."""
    repo = existing_repo(tmp_path / "repo")
    installed_with(
        repo,
        [
            plan_step("p2-lint", "P2", status="done"),
            plan_step("p6-trace", "P6"),
            plan_step("p4-wait", "P4", depends_on=["p6-trace"]),
            plan_step("p4-first", "P4"),
        ],
    )
    assert status(repo).detail == "the adoption plan's next step is p4-first"
    out = run_cli("adopt", "next", str(repo))
    assert out.stdout.startswith("Next: p4-first ")


def test_an_unreadable_project_json_still_routes(tmp_path: Path, git_env: None):
    """/alpha:install routes on status, so a broken project.json mustn't stop
    it; the next step says what is wrong with the file."""
    repo = existing_repo(tmp_path / "repo")
    answers = repo / ".claude/alpha/project.json"
    answers.parent.mkdir(parents=True)
    answers.write_text("{not json")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: Break the answers")
    done = run_cli("status", str(repo))
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("existing")
