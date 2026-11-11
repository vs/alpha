"""alpha adopt apply: alpha's files onto an existing repo (spec §5b, step 5)."""

import json
import os
from datetime import date
from pathlib import Path

import pytest
from helpers import EXISTING, PLUGIN_ROOT, adoption_answers, existing_repo, git, run_cli

from alpha.adopt import AdoptError, AdoptionPlan, apply_adoption, plan_adoption
from alpha.defaults import Source
from alpha.generate import GenerateError
from alpha.gitops import PROPOSALS
from alpha.update import plan_update

SOURCE = Source(PLUGIN_ROOT, True)
TODAY = date(2026, 11, 11)
APP = ("src/legacy/core.py", "tests/test_core.py", "pyproject.toml", "README.md")


@pytest.fixture
def repo(tmp_path: Path, git_env: None) -> Path:
    root = existing_repo(tmp_path / "repo")
    adoption_answers(root)
    return root


def _plan(root: Path) -> AdoptionPlan:
    return plan_adoption(root, PLUGIN_ROOT, SOURCE, TODAY)


def _kinds(root: Path) -> dict[str, str]:
    return {c.path: c.kind for c in _plan(root).update.changes}


def _answers(root: Path, data: dict[str, object]) -> None:
    (root / ".claude/alpha/project.json").write_text(json.dumps(data))


def test_apply_dry_run_writes_nothing(repo: Path):
    before = git(repo, "status", "--porcelain")
    done = run_cli("adopt", "apply", str(repo), "--dry-run")
    assert done.returncode == 0, done.stderr
    assert git(repo, "status", "--porcelain") == before
    kinds = _kinds(repo)
    assert kinds[".gitignore"] == "merge" and kinds[".claude/settings.json"] == "merge"
    assert kinds["README.md"] == "conflict"
    assert kinds[".github/workflows/ci.yml"] == "conflict"
    assert kinds["docs/principles.toml"] == "new"
    assert "LICENSE" not in kinds  # identity.license_file keeps the repo's
    assert "conflict  README.md" in done.stdout


def test_apply_never_loses_a_repo_line(repo: Path):
    apply_adoption(repo, _plan(repo))
    settings = json.loads((repo / ".claude/settings.json").read_text())
    assert "Bash(make test:*)" in settings["permissions"]["allow"]  # JSON, re-laid
    for rel, text in EXISTING.items():
        if rel == ".claude/settings.json":
            continue
        kept = (repo / rel).read_text()
        proposal = repo / PROPOSALS / rel
        where = kept + (proposal.read_text() if proposal.is_file() else "")
        for line in text.splitlines():
            assert line in where, f"{rel}: lost {line!r}"
    for rel in APP:  # app files and conflicted docs stay byte for byte
        assert (repo / rel).read_text() == EXISTING[rel]


def test_records_follow_the_repos(repo: Path):
    records = _plan(repo).update.manifest["records"]["decisions"]
    assert records[0].startswith("docs/decisions/0002-")


def test_apply_makes_the_branch(repo: Path):
    apply_adoption(repo, _plan(repo))
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "alpha/adopt"


def test_existing_adopt_branch_is_refused(repo: Path):
    git(repo, "branch", "alpha/adopt")
    with pytest.raises(AdoptError, match="already exists. Switch to it"):
        apply_adoption(repo, _plan(repo))


def test_apply_stays_on_a_feature_branch(repo: Path):
    git(repo, "switch", "-q", "-c", "feature")
    apply_adoption(repo, _plan(repo))
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "feature"


def test_apply_refuses_a_dirty_tree(repo: Path):
    (repo / "README.md").write_text("edited\n")
    with pytest.raises(AdoptError, match="Commit or stash your changes first"):
        _plan(repo)


def test_apply_refuses_unfinished_answers(repo: Path):
    data = adoption_answers(repo)
    data["areas"]["testing"] = "in_progress"
    _answers(repo, data)
    with pytest.raises(AdoptError, match="areas.testing"):
        _plan(repo)


def test_apply_refuses_a_new_projects_interview(repo: Path):
    data = adoption_answers(repo)
    del data["adoption"]
    _answers(repo, data)
    with pytest.raises(AdoptError, match="/alpha:new-project"):
        _plan(repo)
    data["adoption"] = {}
    _answers(repo, data)
    with pytest.raises(AdoptError, match="adoption.git_hooks is missing"):
        _plan(repo)


def test_apply_refuses_an_adopted_repo(repo: Path):
    apply_adoption(repo, _plan(repo))
    with pytest.raises(AdoptError, match="/alpha:extend"):
        _plan(repo)


def test_apply_writes_a_manifest_update_can_use(repo: Path):
    apply_adoption(repo, _plan(repo))
    data = json.loads((repo / ".claude/alpha/project.json").read_text())
    manifest = data["manifest"]
    assert manifest["adopted_at"] == "2026-11-11"
    assert set(manifest) >= {"applied", "records", "added", "files", "generated_at"}
    state = json.loads((repo / ".claude/alpha/state/update.json").read_text())
    assert state["kind"] == "adopt" and state["new_components"] == []
    with pytest.raises(GenerateError, match="waiting to be committed"):
        plan_update(repo, SOURCE, TODAY)  # like any update, until commit-update


def test_copied_hook_stays_executable(repo: Path):
    apply_adoption(repo, _plan(repo))
    assert os.access(repo / ".claude/alpha/githooks/commit-msg", os.X_OK)


def test_alpha_takes_the_hooks_path(repo: Path):
    apply_adoption(repo, _plan(repo))
    assert git(repo, "config", "core.hooksPath") == ".claude/alpha/githooks"
    contributing = (repo / "CONTRIBUTING.md").read_text()
    assert "git config core.hooksPath .claude/alpha/githooks" in contributing


def test_chain_leaves_git_hooks_alone(repo: Path):
    adoption_answers(repo, git_hooks="chain")
    git(repo, "config", "core.hooksPath", ".husky")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n")
    notes = apply_adoption(repo, _plan(repo))
    assert git(repo, "config", "core.hooksPath") == ".husky"
    assert hook.read_text() == "#!/bin/sh\nexit 0\n"
    assert any('sh .claude/alpha/githooks/commit-msg "$1"' in n for n in notes)
    contributing = (repo / "CONTRIBUTING.md").read_text()
    assert 'sh .claude/alpha/githooks/commit-msg "$1"' in contributing
    assert "git config core.hooksPath" not in contributing
    principles = (repo / "docs/principles.toml").read_text()
    assert 'hooks = "chain"' in principles


def test_git_hooks_answer_validated(repo: Path):
    adoption_answers(repo, git_hooks="husky")
    with pytest.raises(AdoptError, match=r"adoption.git_hooks"):
        _plan(repo)
