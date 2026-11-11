"""alpha adopt survey: an existing repo, described in facts (spec §5b)."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from helpers import PLUGIN_ROOT, git, run_cli

from alpha import adopt
from alpha.adopt import AdoptError, survey
from alpha.defaults import Source

SOURCE = Source(PLUGIN_ROOT, True)


def _repo(
    tmp_path: Path, files: dict[str, str], subjects: list[str] | None = None
) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    for i, subject in enumerate(subjects or ["feat: Start"]):
        (root / ".commit").write_text(str(i))
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", subject)
    return root


@pytest.fixture(autouse=True)
def _identity(git_env: None) -> None:
    pass


def test_survey_finds_components_by_marker(tmp_path: Path):
    root = _repo(
        tmp_path,
        {
            "package.json": "{}",
            "api/pyproject.toml": "",
            "web/package.json": "{}",
            "web/tsconfig.json": "{}",
            ".gitignore": "node_modules/\n",
            "node_modules/x/package.json": "{}",
        },
    )
    found = {
        (c["path"], c["stack"]): c["markers"]
        for c in survey(root, SOURCE)["components"]
    }
    assert found == {
        (".", "typescript"): ["package.json"],
        ("api", "python"): ["api/pyproject.toml"],
        ("web", "typescript"): ["web/package.json", "web/tsconfig.json"],
    }


def test_survey_counts_sources_and_tests(tmp_path: Path):
    root = _repo(
        tmp_path,
        {
            "pyproject.toml": "",
            "tool.py": "",
            "api/pyproject.toml": "",
            "api/app/a.py": "",
            "api/app/b.py": "",
            "api/tests/test_a.py": "",
            "api/.venv/x.py": "",  # an excluded folder, even if tracked
        },
    )
    comps = {c["path"]: c for c in survey(root, SOURCE)["components"]}
    assert (comps["api"]["sources"], comps["api"]["tests"]) == (2, 1)
    assert (comps["."]["sources"], comps["."]["tests"]) == (1, 0)  # not api's files


def test_survey_lists_files(tmp_path: Path):
    root = _repo(
        tmp_path,
        {
            ".github/workflows/ci.yml": "on: push\n",
            "docs/adr/0001-use-postgres.md": "# 1\n",
            ".husky/pre-commit": "npm test\n",
            "LICENSE": "MIT\n",
            "README.md": "# x\n",
            "api/.env.example": "A=1\n",
            "db/migrations/0001.sql": "",
        },
    )
    result = survey(root, SOURCE)
    files = result["files"]
    assert files["ci"] == [".github/workflows/ci.yml"]
    assert files["decisions"] == ["docs/adr/0001-use-postgres.md"]
    assert files["license"] == ["LICENSE"]
    assert "README.md" in files["docs"]
    assert files["env_examples"] == ["api/.env.example"]
    assert files["migrations"] == ["db/migrations/0001.sql"]
    assert result["git"]["hook_managers"] == [".husky/pre-commit"]


def test_survey_caps_long_lists(tmp_path: Path):
    root = _repo(tmp_path, {f"docs/page{i:02d}.md": "# p\n" for i in range(60)})
    files = survey(root, SOURCE)["files"]
    assert len(files["docs"]) == adopt.CAP and files["docs_more"] == 10


def test_survey_git_facts(tmp_path: Path):
    root = _repo(
        tmp_path,
        {"a.txt": "x"},
        ["feat: Add a", "fix(api): Mend b", "wip stuff"],
    )
    git(root, "config", "core.hooksPath", ".githooks")
    (root / "a.txt").write_text("changed")
    facts = survey(root, SOURCE)["git"]
    assert facts["conventional"] == {
        "checked": 3,
        "matching": 2,
        "others": ["wip stuff"],
    }
    assert facts["clean"] is False and facts["dirty"] == ["a.txt"]
    assert facts["hooks_path"] == ".githooks"
    assert facts["branch"] == "main" and facts["default_branch"] == "main"
    assert facts["commits"] == 3


def test_survey_refusals(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(AdoptError, match="isn't a git repository.*git init"):
        survey(plain, SOURCE)
    empty = tmp_path / "empty"
    empty.mkdir()
    git(empty, "init", "-q")
    with pytest.raises(AdoptError, match="no commits yet"):
        survey(empty, SOURCE)
    root = _repo(tmp_path, {"sub/a.txt": "x"})
    with pytest.raises(AdoptError, match="from its root"):
        survey(root / "sub", SOURCE)
    project = root / ".claude/alpha/project.json"
    project.parent.mkdir(parents=True)
    project.write_text(json.dumps({"manifest": {}}))
    with pytest.raises(AdoptError, match="/alpha:extend"):
        survey(root, SOURCE)


def test_survey_reads_one_listing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _repo(tmp_path, {f"src/f{i}.py": "" for i in range(30)})
    calls: list[tuple[str, ...]] = []
    real = adopt._git

    def counting(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return real(target, *args)

    monkeypatch.setattr(adopt, "_git", counting)
    survey(root, SOURCE)
    assert sum(1 for c in calls if c[0] == "ls-files") == 1
    assert len(calls) < 15  # a fixed number of git calls, whatever the repo's size


def test_survey_save_keeps_other_adoption_keys(tmp_path: Path):
    root = _repo(tmp_path, {"pyproject.toml": ""})
    project = root / ".claude/alpha/project.json"
    project.parent.mkdir(parents=True)
    keep: dict[str, Any] = {"schema": 1, "adoption": {"baselines": ["typos"]}}
    project.write_text(json.dumps(keep))
    done = run_cli("adopt", "survey", str(root), "--save")
    assert done.returncode == 0, done.stderr
    saved = json.loads(project.read_text())
    assert saved["adoption"]["baselines"] == ["typos"]
    assert saved["adoption"]["survey"] == json.loads(done.stdout)
    assert saved["schema"] == 1


def test_survey_cli_refusal_exit_code(tmp_path: Path):
    done = run_cli("adopt", "survey", str(tmp_path))
    assert done.returncode == 1 and "git init" in done.stderr
