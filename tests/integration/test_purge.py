"""alpha purge on real repositories (spec, R3.1, R3.3 and R3.4)."""

import json
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
from alpha.status import status

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
    assert not (project / ".claude").exists()  # nothing of the user's was in it
    assert not (project / ".claude/settings.json").exists()  # only alpha's entries
    assert hooks_path(project) is None
    assert git(project, "status", "--porcelain") == ""
    assert "alpha" not in refs(project)
    leftover = subprocess.run(
        ["git", "config", "--get-all", "notes.rewriteRef"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    assert "alpha" not in leftover.stdout
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
    assert "are gone: migrations, review-dates." in done.stdout
    assert "xargs -0 -r betterleaks dir" in (project / "mise.toml").read_text()


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
    readme = EXISTING["README.md"] + "\nCommit with the committer agent.\n"
    repo = existing_repo(
        tmp_path / "repo",
        {**EXISTING, "README.md": readme, ".claude/agents/committer.md": own},
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
    assert "Commit with the committer agent." in (repo / "README.md").read_text()


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


def test_uninstall_then_purge_removes_alpha_in_one_commit(project: Path) -> None:
    before = git(project, "rev-parse", "HEAD")
    assert run_cli("uninstall", str(project)).returncode == 0
    done = run_cli("purge", str(project))
    assert done.returncode == 0, done.stderr
    assert git(project, "rev-parse", "HEAD~1") == before
    assert git(project, "status", "--porcelain") == ""
    assert hooks_path(project) is None


def test_purge_in_a_clone_without_the_recipe_proof(
    tmp_path: Path, git_env: None
) -> None:
    repo = existing_repo(tmp_path / "repo")
    adoption_answers(repo)  # its adopted recipe, proven in this clone only
    install(repo)
    commit(repo, load_project_principles(repo), [])
    (repo / ".claude/alpha/state/proofs.json").unlink()
    (repo / "notes.md").write_text("uncommitted, and not purge's\n")
    done = run_cli("purge", str(repo))
    assert done.returncode == 0, done.stderr
    assert git(repo, "status", "--porcelain").strip() == "?? notes.md"


def test_a_wrapped_depends_stops_purge(project: Path) -> None:
    mise = project / "mise.toml"
    text = mise.read_text()
    line = next(x for x in text.splitlines() if x.startswith('depends = ["check:'))
    names = line.removeprefix("depends = [").removesuffix("]").split(", ")
    wrapped = "depends = [\n" + "".join(f"  {n},\n" for n in names) + "]"
    mise.write_text(text.replace(line, wrapped, 1))
    git(project, "commit", "-q", "-am", "build: Wrap the ci depends")
    head = git(project, "rev-parse", "HEAD")
    done = run_cli("purge", str(project))
    assert done.returncode == 1
    assert "check:migrations" in done.stderr and "wrote nothing" in done.stderr
    assert git(project, "rev-parse", "HEAD") == head


def test_purge_keeps_the_repos_own_permission_rules(
    tmp_path: Path, git_env: None
) -> None:
    own = {"permissions": {"allow": ["Bash(git status:*)", "Bash(make *)"]}}
    repo = existing_repo(
        tmp_path / "repo", {**EXISTING, ".claude/settings.json": json.dumps(own)}
    )
    head = git(repo, "rev-parse", "HEAD")
    adoption_answers(repo, survey={"git": {"head": head}})
    install(repo)
    shutil.rmtree(repo / ".claude/alpha/state/update", ignore_errors=True)
    commit(repo, load_project_principles(repo), [])
    done = run_cli("purge", str(repo))
    assert done.returncode == 0, done.stderr
    kept = json.loads((repo / ".claude/settings.json").read_text())
    assert kept["permissions"]["allow"] == ["Bash(git status:*)", "Bash(make *)"]


def test_a_refused_purge_leaves_the_hooks_off(project: Path) -> None:
    assert run_cli("uninstall", str(project)).returncode == 0
    claude = project / "CLAUDE.md"
    claude.write_text(claude.read_text() + "\n- Uncommitted rule.\n")
    done = run_cli("purge", str(project))
    assert done.returncode == 1 and "CLAUDE.md has uncommitted changes" in done.stderr
    assert status(project).name == "hooks-off"
    settings = (project / ".claude/settings.json").read_text()
    assert ".claude/alpha/hooks/" not in settings


def test_a_depends_on_a_task_outside_mise_toml_stays(project: Path) -> None:
    mise = project / "mise.toml"
    mise.write_text(mise.read_text() + '\n[tasks.release]\ndepends = ["build"]\n')
    git(project, "commit", "-q", "-am", "build: Release after the build file task")
    done = run_cli("purge", str(project))
    assert done.returncode == 0, done.stderr
    assert 'depends = ["build"]' in mise.read_text()


def test_a_purge_refused_by_the_answers_leaves_the_hooks_off(project: Path) -> None:
    """A refusal from outside alpha's own error type (here the answers'
    check) undoes nothing of the uninstall either."""
    assert run_cli("uninstall", str(project)).returncode == 0
    path = project / ".claude/alpha/project.json"
    data = json.loads(path.read_text())
    data["decisions"] = []
    path.write_text(json.dumps(data))
    done = run_cli("purge", str(project))
    assert done.returncode == 1 and "decisions" in done.stderr
    assert status(project).name == "hooks-off"
    assert ".claude/alpha/hooks/" not in (project / ".claude/settings.json").read_text()
