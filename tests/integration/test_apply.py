"""alpha apply on an empty folder: a new project's files (rewrite spec, R1.1)."""

import re
from pathlib import Path

from helpers import generated_repo, git, install, place_answers, run_cli

from alpha.answers import PROJECT_JSON
from alpha.cli import PLUGIN_ROOT

SCENARIO = "web-ts-plus-python-api"
# A digest a committed file must never hold (requirement 16).
HASH = re.compile(r"sha256:|\b[0-9a-f]{40}\b|\b[0-9a-f]{64}\b|proven_hash")


def test_R1_1_a_new_project_gets_the_layout(tmp_path: Path):
    place_answers(tmp_path, SCENARIO)
    written = install(tmp_path)
    for rel in (
        "CLAUDE.md",
        "README.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "mise.toml",
        ".gitignore",
        ".github/workflows/ci.yml",
        "docs/alpha/principles.toml",
        "docs/alpha/dependencies.md",
        "docs/alpha/specification.md",
        ".claude/settings.json",
        ".claude/agents/principles-reviewer.md",
        ".claude/alpha/hooks/stop_checks.py",
        ".claude/alpha/githooks/commit-msg",
        "api/pyproject.toml",
        "web/package.json",
    ):
        assert rel in written, rel
    assert not [f for f in written if "/src/" in f or f.startswith("src/")]
    assert git(tmp_path, "branch", "--show-current") == "main"


def test_R6_1_docs_go_to_contributing_and_docs_alpha(tmp_path: Path):
    place_answers(tmp_path, SCENARIO)
    written = install(tmp_path)
    in_docs = sorted(f for f in written if f.startswith("docs/"))
    assert all(f.startswith("docs/alpha/") for f in in_docs), in_docs
    contributing = (tmp_path / "CONTRIBUTING.md").read_text()
    for heading in (
        "## Components",
        "## Checks",
        "## Testing",
        "## Documentation",
        "## Branching",
        "## Build, CI and hosting",
        "## Releases",
        "### Secrets",
        "### Protected paths",
        "## Overrides",
        "## Exceptions",
    ):
        assert heading in contributing, heading


def test_R12_5_projects_get_the_agents_and_skills(tmp_path: Path):
    place_answers(tmp_path, SCENARIO)
    install(tmp_path)
    copied = [f".claude/agents/{a}.md" for a in ("principles-reviewer", "committer")]
    copied += [
        f".claude/skills/{s}/SKILL.md"
        for s in ("commit", "decision", "review-change", "audit")
    ]
    for rel in copied:
        text = (tmp_path / rel).read_text()
        assert "docs/decisions" not in text, rel
        assert not re.search(r"(?<!alpha/)docs/(specification|principles)\.", text), rel
        assert "/alpha:go" not in text, rel
    reviewer = (tmp_path / ".claude/agents/principles-reviewer.md").read_text()
    for piece in ('"checked"', "`Kind: fix-check`", '"Review afresh"'):
        assert piece in reviewer, piece
    assert (
        "Stop hook" not in reviewer and "after a planned piece of work" not in reviewer
    )
    decision = (tmp_path / ".claude/skills/decision/SKILL.md").read_text()
    assert "`/alpha:specify`" in decision


def test_R13_2_commit_msg_is_the_only_git_hook(tmp_path: Path):
    place_answers(tmp_path, SCENARIO)
    install(tmp_path)
    hooks = sorted(p.name for p in (tmp_path / ".claude/alpha/githooks").iterdir())
    assert hooks == ["commit-msg"]
    assert git(tmp_path, "config", "core.hooksPath") == ".claude/alpha/githooks"


def test_R16_1_no_committed_file_holds_file_hashes(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    data = (target / PROJECT_JSON).read_text()
    assert "manifest" not in data

    def project_hashes(rel: str) -> bool:
        # CI pins each action to its commit (a `uses:` line): an upstream
        # commit, not one of this project's files.
        lines = (target / rel).read_text(errors="replace").splitlines()
        return any(HASH.search(line) for line in lines if "uses:" not in line)

    found = [
        rel
        for rel in git(target, "ls-files").splitlines()
        if not rel.startswith((".claude/alpha/hooks/", ".claude/alpha/checks/"))
        and rel not in ("uv.lock", "web/pnpm-lock.yaml")
        and project_hashes(rel)
    ]
    assert found == []
    assert git(target, "rev-parse", "--verify", "refs/alpha/rendered")
    assert str(PLUGIN_ROOT) not in data


def test_a_new_project_is_told_one_next_step(tmp_path: Path):
    place_answers(tmp_path, SCENARIO)
    done = run_cli("apply", str(tmp_path))
    assert done.returncode == 0, done.stderr
    assert "New components" not in done.stdout
    assert f'Next: "alpha bootstrap {tmp_path}", then "alpha commit' in done.stdout
