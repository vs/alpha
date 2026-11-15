"""alpha purge on real repositories (rewrite spec, R3.1, R3.3 and R3.4)."""

import shutil
import subprocess
from pathlib import Path

import pytest
from helpers import (
    EXISTING,
    adoption_answers,
    existing_repo,
    generated_repo,
    git,
    install,
    run_cli,
)

from alpha.generate import load_project_principles
from alpha.gitops import commit

ALPHA_PATHS = (".claude/alpha/", "docs/alpha/")
KEPT_FILES_ALPHA_WROTE = (
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "README.md",
    "_typos.toml",
    ".rumdl.toml",
    "lychee.toml",
    "mise.toml",
    ".github/workflows/ci.yml",
    ".github/workflows/scheduled.yml",
    ".gitignore",
)


def changed_in_head(repo: Path) -> set[str]:
    return set(git(repo, "show", "--name-only", "--format=", "HEAD").splitlines())


def hooks_path(repo: Path) -> str | None:
    done = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else None


def refs(repo: Path) -> str:
    return git(repo, "for-each-ref", "--format=%(refname)")


@pytest.fixture
def project(tmp_path: Path, git_env: None) -> Path:
    return generated_repo(tmp_path / "p", "web-ts-plus-python-api")


def test_R3_1_purge_removes_alpha_in_one_commit(project: Path) -> None:
    skill = project / ".claude/skills/commit/SKILL.md"
    skill.write_text(skill.read_text() + "\nOur own note.\n")
    spec = project / "docs/alpha/specification.md"
    spec.write_text(spec.read_text() + "\nHand-written.\n")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "docs: Add our notes")
    before = git(project, "rev-parse", "HEAD")
    assert "refs/alpha/rendered" in refs(project)
    done = run_cli("purge", str(project), "--trailer", "Reviewed-by: Dana")
    assert done.returncode == 0, done.stderr
    assert git(project, "rev-parse", "HEAD~1") == before
    assert git(project, "log", "-1", "--format=%s") == "chore: Remove alpha"
    assert "Reviewed-by: Dana" in git(project, "log", "-1", "--format=%b")
    for gone in (".claude/alpha", "docs/alpha", ".claude/agents", ".claude/skills"):
        assert not (project / gone).exists(), gone
    assert not (project / ".claude/settings.json").exists()  # only alpha's entries
    assert hooks_path(project) is None
    assert git(project, "status", "--porcelain") == ""
    assert "alpha" not in refs(project)
    changed = changed_in_head(project)
    assert {
        ".claude/skills/commit/SKILL.md",
        "docs/alpha/specification.md",
        ".claude/settings.json",
        "CLAUDE.md",
        "mise.toml",
    } <= changed
    assert all(
        p.startswith((*ALPHA_PATHS, ".claude/")) or p in KEPT_FILES_ALPHA_WROTE
        for p in changed
    ), changed
    assert "secrets, migrations, review-dates" in done.stdout


def test_R3_3_no_kept_file_names_a_deleted_path(project: Path) -> None:
    tracked = set(git(project, "ls-files").splitlines())
    assert run_cli("purge", str(project)).returncode == 0
    deleted = tracked - set(git(project, "ls-files").splitlines())
    for rel in git(project, "ls-files").splitlines():
        text = (project / rel).read_text(errors="replace").replace("\\", "")
        assert not any(d in text for d in ALPHA_PATHS), rel
        assert not any(d in text for d in deleted if "/" in d), rel


def test_R3_3_an_uncleanable_file_stops_purge(project: Path) -> None:
    mise = project / "mise.toml"
    text = mise.read_text()
    run = 'run = "python3 .claude/alpha/checks/review_dates.py"'
    task = f'[tasks."check:review-dates"]\n{run}\n\n'
    assert task in text
    inline = f'"check:review-dates" = {{ {run} }}\n'  # the same task, reformatted
    mise.write_text(text.replace(task, "").replace("[tasks]\n", f"[tasks]\n{inline}"))
    git(project, "commit", "-q", "-am", "build: Inline the review-dates task")
    head = git(project, "rev-parse", "HEAD")
    line = mise.read_text().splitlines().index(inline.rstrip()) + 1
    done = run_cli("purge", str(project))
    assert done.returncode == 1
    assert f"mise.toml:{line}" in done.stderr and "wrote nothing" in done.stderr
    assert git(project, "rev-parse", "HEAD") == head
    assert git(project, "status", "--porcelain") == ""
    assert hooks_path(project) == ".claude/alpha/githooks"


def test_R3_4_purge_commits_only_alphas_paths(project: Path) -> None:
    (project / "README.md").write_text("Our own README, not yet committed.\n")
    (project / "notes.txt").write_text("scratch\n")
    claude = project / "CLAUDE.md"
    claude.write_text(claude.read_text() + "\n- Uncommitted rule.\n")
    refused = run_cli("purge", str(project))
    assert refused.returncode == 1
    assert "CLAUDE.md has uncommitted changes" in refused.stderr
    assert (project / ".claude/alpha").is_dir()
    git(project, "checkout", "--", "CLAUDE.md")
    done = run_cli("purge", str(project))
    assert done.returncode == 0, done.stderr
    assert "README.md" not in changed_in_head(project)
    status = git(project, "status", "--porcelain").splitlines()
    assert sorted(s.strip() for s in status) == ["?? notes.txt", "M README.md"]


def test_R3_4_purge_keeps_the_repos_own_files(tmp_path: Path, git_env: None) -> None:
    own = "# Our committer\n\nWe commit our own way.\n"
    repo = existing_repo(
        tmp_path / "repo", {**EXISTING, ".claude/agents/committer.md": own}
    )
    adoption_answers(repo)
    install(repo)
    # The user merges alpha's proposal for their committer by keeping theirs.
    shutil.rmtree(repo / ".claude/alpha/state/update", ignore_errors=True)
    (repo / ".claude/agents/committer.md").write_text(own)
    commit(repo, load_project_principles(repo), [])
    done = run_cli("purge", str(repo))
    assert done.returncode == 0, done.stderr
    assert (repo / ".claude/agents/committer.md").read_text() == own
    assert not (repo / ".claude/agents/principles-reviewer.md").exists()


def test_ratcheted_checks_run_plain_after_purge(tmp_path: Path, git_env: None) -> None:
    repo = existing_repo(tmp_path / "repo")
    adoption_answers(repo, baselines=["typecheck:ml", "typos"])
    install(repo)
    commit(repo, load_project_principles(repo), [])
    mise = (repo / "mise.toml").read_text()
    assert ".claude/alpha/checks/ratchet.py typecheck:ml" in mise
    done = run_cli("purge", str(repo))
    assert done.returncode == 0, done.stderr
    assert "now report the legacy findings again: typecheck:ml, typos" in done.stdout
    mise = (repo / "mise.toml").read_text()
    assert "ratchet.py" not in mise
    assert '[tasks."check:typos"]\nrun = "typos"' in mise


def test_purge_takes_the_chained_call_out_of_the_hook_managers_file(
    tmp_path: Path, git_env: None
) -> None:
    repo = existing_repo(tmp_path / "repo")
    adoption_answers(repo, git_hooks="chain")
    install(repo)
    hook = repo / ".husky/commit-msg"
    hook.parent.mkdir()
    ours = '#!/bin/sh\nset -e\necho "husky"\n'
    alphas = '# alpha:begin\nsh .claude/alpha/githooks/commit-msg "$1"\n# alpha:end\n'
    hook.write_text(ours + alphas)
    hook.chmod(0o755)
    git(repo, "config", "core.hooksPath", ".husky")
    commit(repo, load_project_principles(repo), [])
    git(repo, "add", ".husky/commit-msg")
    git(repo, "commit", "-q", "-m", "build: Chain alpha's commit check")
    done = run_cli("purge", str(repo))
    assert done.returncode == 0, done.stderr
    assert hook.read_text() == ours
    assert ".husky/commit-msg" in changed_in_head(repo)
    assert hooks_path(repo) == ".husky"
    assert git(repo, "status", "--porcelain") == ""


def test_purge_needs_an_installed_project(tmp_path: Path) -> None:
    done = run_cli("purge", str(tmp_path))
    assert done.returncode == 1
    assert "nothing to purge" in done.stderr
