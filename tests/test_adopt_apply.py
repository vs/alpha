"""alpha adopt apply: alpha's files onto an existing repo (spec §5b, step 5)."""

import json
import os
from datetime import date
from pathlib import Path

import pytest
from helpers import EXISTING, PLUGIN_ROOT, adoption_answers, existing_repo, git, run_cli

from alpha.adopt import AdoptError, AdoptionPlan, apply_adoption, plan_adoption
from alpha.defaults import Source
from alpha.generate import GenerateError, load_project_principles
from alpha.gitops import PROPOSALS, commit_update
from alpha.update import apply_update, describe, plan_update

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


def test_apply_refuses_when_git_status_fails(repo: Path):
    (repo / ".git" / "index").write_bytes(b"not an index")
    with pytest.raises(GenerateError, match=r"git status failed in .*, so alpha"):
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


def _resolve(root: Path, plan: AdoptionPlan) -> None:
    """A stand-in for Claude's hand merge: the repo's file, then alpha's."""
    for c in plan.update.changes:
        if c.kind == "conflict":
            rendered = (root / PROPOSALS / c.path).read_text()
            (root / c.path).write_text(EXISTING[c.path] + "\n" + rendered)


def test_commit_adoption_groups(repo: Path):
    plan = _plan(repo)
    apply_adoption(repo, plan)
    _resolve(repo, plan)
    baseline = repo / ".claude/alpha/baselines/typos.json"
    baseline.parent.mkdir(parents=True)
    baseline.write_text('{"check": "typos", "counts": {}}\n')
    start = git(repo, "rev-parse", "HEAD")
    hashes, _ = commit_update(
        repo, load_project_principles(repo), ["Co-Authored-By: T <t@example.com>"]
    )
    subjects = git(repo, "log", "--format=%s", f"{start}..HEAD").splitlines()
    assert list(reversed(subjects)) == [
        "docs: Add product brief, principles and decisions",
        "chore: Add Claude Code settings and guardrails",
        "build: Pin the repository's check tools",
        "ci: Run every component's checks in CI",
        "ci: Schedule dependency updates",  # the scenario chose Dependabot
    ]
    assert len(hashes) == 5
    body = git(repo, "log", "-1", "--format=%B")
    assert body.rstrip().endswith("Co-Authored-By: T <t@example.com>")
    chore = git(repo, "show", "--name-only", "--format=", hashes[1]).splitlines()
    assert ".claude/alpha/baselines/typos.json" in chore
    assert ".claude/alpha/project.json" in chore
    touched = git(repo, "diff", "--name-only", start, "HEAD").splitlines()
    assert not set(touched) & {
        "src/legacy/core.py",
        "tests/test_core.py",
        "pyproject.toml",
    }
    assert git(repo, "status", "--porcelain") == ""


def _adopted(repo: Path) -> None:
    plan = _plan(repo)
    apply_adoption(repo, plan)
    _resolve(repo, plan)
    commit_update(repo, load_project_principles(repo), [])


def test_update_after_adoption(repo: Path):
    _adopted(repo)
    assert describe(plan_update(repo, SOURCE, TODAY), repo) == (
        "alpha update: nothing to change"
    )
    path = repo / ".claude/alpha/project.json"
    data = json.loads(path.read_text())
    data["releases"]["changelog"] = (
        "file" if data["releases"]["changelog"] != "file" else "none"
    )
    path.write_text(json.dumps(data, indent=2))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--no-verify", "-m", "chore: Change the changelog")
    plan = plan_update(repo, SOURCE, TODAY)
    kinds = {c.path: c.kind for c in plan.changes}
    assert "conflict" not in kinds.values(), kinds
    if "README.md" in kinds:
        apply_update(repo, plan)
        readme = (repo / "README.md").read_text()
        assert EXISTING["README.md"].strip() in readme  # the repo's lines stay


def test_update_refusal_points_to_adopt(tmp_path: Path, git_env: None):
    root = existing_repo(tmp_path / "plain")
    with pytest.raises(GenerateError, match="/alpha:adopt"):
        plan_update(root, SOURCE, TODAY)


def test_apply_refuses_a_repo_that_ignores_alphas_files(repo: Path):
    (repo / ".gitignore").write_text(EXISTING[".gitignore"] + ".claude/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "chore: Ignore Claude Code")
    with pytest.raises(AdoptError, match="ignore rules cover files alpha must") as e:
        _plan(repo)
    assert ".gitignore:4:.claude/" in str(e.value)
    assert ".claude/settings.local.json only" in str(e.value)


def test_apply_refuses_a_detached_head(repo: Path):
    git(repo, "checkout", "-q", "--detach")
    with pytest.raises(AdoptError, match="HEAD is detached"):
        apply_adoption(repo, _plan(repo))


def test_alpha_mode_refuses_to_replace_the_repos_hooks(repo: Path):
    git(repo, "config", "core.hooksPath", ".githooks")
    with pytest.raises(AdoptError, match='core.hooksPath is .githooks.*"chain"'):
        _plan(repo)
    git(repo, "config", "--unset", "core.hooksPath")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n")
    with pytest.raises(AdoptError, match="holds pre-commit"):
        _plan(repo)
