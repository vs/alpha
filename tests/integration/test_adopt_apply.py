"""alpha adopt apply: alpha's files onto an existing repo (spec §5b, step 5)."""

import json
import os
import shutil
from datetime import date
from pathlib import Path

import pytest
from helpers import (
    EXISTING,
    PLUGIN_ROOT,
    adoption_answers,
    existing_repo,
    git,
    place_rust_monorepo,
    run_cli,
)

from alpha.adopt import AdoptError, apply_adoption, plan_adoption
from alpha.defaults import Source
from alpha.generate import GenerateError, load_project_principles
from alpha.gitops import PROPOSALS, commit_update
from alpha.update import UpdatePlan, apply_update, describe, plan_update

SOURCE = Source(PLUGIN_ROOT, True)
TODAY = date(2026, 11, 11)
APP = ("src/legacy/core.py", "tests/test_core.py", "pyproject.toml", "README.md")


@pytest.fixture
def repo(tmp_path: Path, git_env: None) -> Path:
    root = existing_repo(tmp_path / "repo")
    adoption_answers(root)
    return root


def _plan(root: Path) -> UpdatePlan:
    return plan_adoption(root, PLUGIN_ROOT, SOURCE, TODAY)


def _kinds(root: Path) -> dict[str, str]:
    return {c.path: c.kind for c in _plan(root).changes}


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
    records = _plan(repo).manifest["records"]["decisions"]
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
        plan_update(
            repo, PLUGIN_ROOT, SOURCE, TODAY
        )  # like any update, until commit-update


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


def _resolve(root: Path, plan: UpdatePlan) -> None:
    """A stand-in for Claude's hand merge: the repo's file, then alpha's."""
    for c in plan.changes:
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
    assert describe(plan_update(repo, PLUGIN_ROOT, SOURCE, TODAY), repo) == (
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
    plan = plan_update(repo, PLUGIN_ROOT, SOURCE, TODAY)
    kinds = {c.path: c.kind for c in plan.changes}
    assert "conflict" not in kinds.values(), kinds
    if "README.md" in kinds:
        apply_update(repo, plan)
        readme = (repo / "README.md").read_text()
        assert EXISTING["README.md"].strip() in readme  # the repo's lines stay


def _older_kit(folder: Path, version: str) -> Path:
    """A copy of this kit that calls itself `version`, as an older alpha."""
    for part in ("src", "defaults", "recipes", "registry", "project-files"):
        shutil.copytree(
            PLUGIN_ROOT / part,
            folder / part,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    (folder / "src/alpha/__init__.py").write_text(f'VERSION: str = "{version}"\n')
    return folder


def test_kit_upgrade_brings_the_kits_changes_and_keeps_the_repos(
    repo: Path, tmp_path: Path
):
    """Spec §5a: the older kit renders what it wrote, so only its changes
    come through, and the repo's lines and edits stay."""
    _adopted(repo)
    kit = _older_kit(tmp_path / "old-kit", "0.0.1")
    rel = ".claude/alpha/hooks/guard_bash.py"
    current = (PLUGIN_ROOT / "project-files/hooks/guard_bash.py").read_text()
    older = current + "# written by the older kit\n"
    (kit / "project-files/hooks/guard_bash.py").write_text(older)
    (repo / rel).write_text(older)  # as that kit wrote it
    path = repo / ".claude/alpha/project.json"
    data = json.loads(path.read_text())
    data["manifest"]["kit_version"] = "0.0.1"
    data["manifest"]["defaults"] = {"path": str(kit), "live": True, "commit": None}
    path.write_text(json.dumps(data, indent=2) + "\n")
    record = repo / data["manifest"]["records"]["decisions"][0]
    record.write_text(
        record.read_text().replace("Status: accepted", "Status: superseded by 0099")
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--no-verify", "-m", "chore: As the older kit left it")
    plan = plan_update(repo, PLUGIN_ROOT, SOURCE, TODAY)
    assert {c.path: c.kind for c in plan.changes} == {rel: "change"}
    assert describe(plan, repo).startswith("alpha update (kit 0.0.1 to ")
    apply_update(repo, plan)
    assert (repo / rel).read_text() == current
    assert "Status: superseded by 0099" in record.read_text()
    assert EXISTING["README.md"].strip() in (repo / "README.md").read_text()
    assert json.loads(path.read_text())["manifest"]["kit_version"] != "0.0.1"


def test_kit_upgrade_without_the_older_kit_says_where_to_put_it(repo: Path):
    _adopted(repo)
    path = repo / ".claude/alpha/project.json"
    data = json.loads(path.read_text())
    data["manifest"]["kit_version"] = "0.0.1"
    path.write_text(json.dumps(data, indent=2) + "\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--no-verify", "-m", "chore: As an older kit left it")
    with pytest.raises(GenerateError, match=r"alpha 0\.0\.1 set .* that kit isn't"):
        plan_update(repo, PLUGIN_ROOT, SOURCE, TODAY)


def test_update_refusal_points_to_adopt(tmp_path: Path, git_env: None):
    root = existing_repo(tmp_path / "plain")
    with pytest.raises(GenerateError, match="/alpha:adopt"):
        plan_update(root, PLUGIN_ROOT, SOURCE, TODAY)


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


# --- components with no project structure yet ---

DOCS_ONLY = {
    "README.md": "# Tool\n\nThe design is in docs/design.md.\n",
    "docs/design.md": "# Design\n\nA cli and a core in Rust, and a Python api.\n",
    "core/notes.md": "# Core\n\nWhat the core will own.\n",
}


def _docs_only(root: Path, files: dict[str, str] | None = None) -> Path:
    """A repo that holds docs and no code: its components (the Rust `cli` and
    `core`, the Python `api`) are on the kit's recipes."""
    existing_repo(root, {**DOCS_ONLY, **(files or {})})
    answers = place_rust_monorepo(root)
    data = json.loads(answers.read_text())
    data["adoption"] = {"git_hooks": "alpha"}
    answers.write_text(json.dumps(data))
    return root


@pytest.fixture
def docs_only(tmp_path: Path, git_env: None) -> Path:
    return _docs_only(tmp_path / "docs-only")


def test_apply_writes_the_skeleton_of_a_component_with_no_manifest(docs_only: Path):
    plan = _plan(docs_only)
    assert plan.new_components == ("cli", "core", "api")
    kinds = {c.path: c.kind for c in plan.changes}
    for rel in ("Cargo.toml", "core/Cargo.toml", "cli/tests/setup.rs"):
        assert kinds[rel] == "new", rel
    assert kinds["api/pyproject.toml"] == "new"
    apply_adoption(docs_only, plan)
    assert (docs_only / "core/Cargo.toml").is_file()
    assert (docs_only / "core/notes.md").read_text() == DOCS_ONLY["core/notes.md"]
    state = json.loads((docs_only / ".claude/alpha/state/update.json").read_text())
    assert state["new_components"] == ["cli", "core", "api"]


def test_dry_run_names_the_new_components_and_the_bootstrap(docs_only: Path):
    done = run_cli("adopt", "apply", str(docs_only), "--dry-run")
    assert done.returncode == 0, done.stderr
    assert (
        f"New components: cli, core, api. Then run: alpha bootstrap {docs_only} "
        "--capture-baselines"
    ) in done.stdout
    assert not (docs_only / "core/Cargo.toml").exists()


def test_a_component_whose_manifest_exists_is_not_new(tmp_path: Path, git_env: None):
    mine = '[project]\nname = "api"\nversion = "1.0"\n'
    root = _docs_only(tmp_path / "repo", {"api/pyproject.toml": mine})
    plan = _plan(root)
    assert plan.new_components == ("cli", "core")
    kinds = {c.path: c.kind for c in plan.changes}
    assert kinds["api/pyproject.toml"] == "conflict"
    apply_adoption(root, plan)
    assert (root / "api/pyproject.toml").read_text() == mine


def _header(line: str) -> tuple[str, str, str]:
    return line.partition(" ")


def test_commit_adoption_commits_each_new_skeleton_whole(docs_only: Path):
    plan = _plan(docs_only)
    apply_adoption(docs_only, plan)
    for c in plan.changes:
        if c.kind == "conflict":  # Claude's hand merge: the repo's, then alpha's
            mine = (docs_only / c.path).read_text()
            alphas = (docs_only / PROPOSALS / c.path).read_text()
            (docs_only / c.path).write_text(mine + "\n" + alphas)
    (docs_only / "Cargo.lock").write_text("version = 4\n")  # as cargo fetch writes
    (docs_only / "api/uv.lock").write_text("version = 1\n")  # as uv sync writes
    start = git(docs_only, "rev-parse", "HEAD")
    commit_update(docs_only, load_project_principles(docs_only), [])
    assert git(docs_only, "status", "--porcelain") == ""
    log = git(docs_only, "log", "--reverse", "--format=%H %s", f"{start}..HEAD")
    commits = {subject: sha for sha, _, subject in map(_header, log.splitlines())}
    assert [s for s in commits if s.startswith("build")] == [
        "build: Pin the repository's check tools",
        "build: Set up the rust workspace and tests",
        "build(api): Set up python toolchain and tests",
    ]

    def files(subject: str) -> set[str]:
        shown = git(docs_only, "show", "--name-only", "--format=", commits[subject])
        return set(shown.splitlines())

    # The workspace's root files list every member, so they pass only together.
    assert files("build: Set up the rust workspace and tests") == {
        "Cargo.toml",
        "Cargo.lock",
        "clippy.toml",
        "rust-toolchain.toml",
        "cli/Cargo.toml",
        "cli/tests/setup.rs",
        "core/Cargo.toml",
        "core/tests/setup.rs",
    }
    assert "api/uv.lock" in files("build(api): Set up python toolchain and tests")


def test_commit_adoption_of_a_new_root_component_leaves_a_clean_tree(
    tmp_path: Path, git_env: None
):
    root = existing_repo(tmp_path / "single", DOCS_ONLY)
    data = adoption_answers(root)
    data["components"][0]["stack"] = "python"
    data["identity"]["license_file"] = None
    del data["recipes"]
    _answers(root, data)
    plan = _plan(root)
    assert plan.new_components == ("ml",)
    apply_adoption(root, plan)
    (root / "README.md").write_text((root / PROPOSALS / "README.md").read_text())
    (root / "uv.lock").write_text("version = 1\n")  # as uv sync writes
    commit_update(root, load_project_principles(root), [])
    assert git(root, "status", "--porcelain") == ""
    assert "uv.lock" in git(root, "ls-files").splitlines()
