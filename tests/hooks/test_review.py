import json
import os
import subprocess
import sys
import time
from typing import Any

import pytest
import review

from .conftest import HOOKS, Project


def commit_all(project: Project, message: str = "chore: Base") -> None:
    project.git("add", "-A")
    project.git("commit", "-q", "--allow-empty", "-m", message)


def base(project: Project) -> dict[str, Any]:
    project.write("api/pyproject.toml", "[project]\nname = 'x'\n")
    project.write("web/package.json", "{}\n")
    commit_all(project)
    return review.ensure_state(project.root)


def tree_of(project: Project, rev: str) -> str:
    return project.git("rev-parse", f"{rev}^{{tree}}").stdout.strip()


def lines(n: int) -> str:
    return "".join(f"x{i} = {i}\n" for i in range(n))


def test_fresh_state_starts_at_head(project: Project) -> None:
    state = base(project)
    assert state["reviewed_tree"] == tree_of(project, "HEAD")
    assert review.debt(project.root, project.principles())["files"] == []


def test_fresh_state_without_commits_is_the_empty_tree(project: Project) -> None:
    state = review.ensure_state(project.root)
    assert state["reviewed_tree"] == review.EMPTY_TREE


def test_snapshot_ignores_gitignored_and_state_and_leaves_index_alone(
    project: Project,
) -> None:
    base(project)
    project.write(".gitignore", "*.log\n.claude/alpha/state/\n")
    commit_all(project, "chore: Ignore logs")
    review.ensure_state(project.root)
    state = review.load_state(project.root)
    state["reviewed_tree"] = tree_of(project, "HEAD")
    review.save_state(project.root, state)
    project.write("run.log", "noise\n")
    project.write(".claude/alpha/state/anything", "x\n")
    project.write("api/src/x.py", "x = 1\n")
    project.git("add", "api/src/x.py")
    staged = project.git("diff", "--cached", "--name-only").stdout
    debt = review.debt(project.root, project.principles())
    assert debt["files"] == ["api/src/x.py"]
    assert project.git("diff", "--cached", "--name-only").stdout == staged


def test_debt_counts_untracked_and_modified(project: Project) -> None:
    base(project)
    project.write("api/src/new.py", lines(3))
    project.write("web/package.json", '{"a": 1}\n')
    debt = review.debt(project.root, project.principles())
    assert sorted(debt["files"]) == ["api/src/new.py", "web/package.json"]
    assert debt["counted_lines"] == 3 + 2
    assert debt["counted_files"] == 2


def test_excluded_paths_do_not_count_toward_size(project: Project) -> None:
    base(project)
    project.write("api/tests/test_big.py", lines(500))
    project.write("docs/notes.md", lines(50))
    debt = review.debt(project.root, project.principles())
    assert debt["counted_lines"] == 0 and debt["counted_files"] == 0
    assert len(debt["files"]) == 2


def test_batched_triggers_on_lines(project: Project) -> None:
    base(project)
    project.write("api/src/big.py", lines(201))
    reason = review.review_due(
        project.principles(), review.debt(project.root, project.principles())
    )
    assert reason == (
        "201 lines in 1 files changed since the last review "
        "(limits: max_lines 200, max_files 5)"
    )


def test_batched_triggers_on_files(project: Project) -> None:
    base(project)
    for i in range(5):
        project.write(f"api/src/m{i}.py", "x = 1\n")
    reason = review.review_due(
        project.principles(), review.debt(project.root, project.principles())
    )
    assert reason is not None and "5 files" in reason


def test_small_changes_need_no_review(project: Project) -> None:
    base(project)
    project.write("api/src/m.py", lines(10))
    debt = review.debt(project.root, project.principles())
    assert review.review_due(project.principles(), debt) is None


def test_risky_paths_trigger_regardless_of_size(project: Project) -> None:
    base(project)
    project.write("api/openapi.yaml", "openapi: 3.1.0\n")
    debt = review.debt(project.root, project.principles())
    assert debt["risky"] == ["api/openapi.yaml"]
    assert review.review_due(project.principles(), debt) == (
        "risky paths changed: api/openapi.yaml"
    )


def test_manifest_and_new_component_folder_are_risky(project: Project) -> None:
    project.write("api/pyproject.toml", "[project]\n")
    commit_all(project)
    review.ensure_state(project.root)
    project.write("api/pyproject.toml", "[project]\nname = 'y'\n")
    project.write("web/src/app.ts", "export {}\n")
    debt = review.debt(project.root, project.principles())
    assert debt["risky"] == ["api/pyproject.toml", "web/src/app.ts"]


def test_every_task_triggers_on_any_change(project: Project) -> None:
    base(project)
    data = project.principles()
    data["review"]["mode"] = "every-task"
    project.write_principles(data)
    commit_all(project, "chore: Every task")
    state = review.load_state(project.root)
    state["reviewed_tree"] = tree_of(project, "HEAD")
    review.save_state(project.root, state)
    project.write("api/tests/test_a.py", "x = 1\n")
    debt = review.debt(project.root, project.principles())
    assert review.review_due(project.principles(), debt) == "review mode is every-task"


def test_unreadable_state_is_treated_as_fresh(project: Project) -> None:
    base(project)
    path = project.root / ".claude/alpha/state/review.json"
    path.write_text("{not json")
    assert review.load_state(project.root) == {"unreadable": True}
    assert review.ensure_state(project.root)["reviewed_tree"] == tree_of(
        project, "HEAD"
    )
    assert json.loads(path.read_text())["findings"] == []


def decision(
    project: Project, number: int, title: str, status: str = "accepted"
) -> None:
    slug = title.lower().replace(" ", "-")
    project.write(
        f"docs/decisions/{number:04d}-{slug}.md",
        f"# {number:04d}. {title}\n\nDate: 2026-10-23\nStatus: {status}\n\n"
        "## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nq\n",
    )


def briefed(project: Project) -> str:
    project.write("api/pyproject.toml", "[project]\nname = 'x'\n")
    project.write("web/package.json", "{}\n")
    decision(project, 1, "Use OpenAPI")
    decision(project, 2, "Use REST", status="superseded by 0003")
    decision(project, 3, "Use gRPC")
    commit_all(project)
    review.ensure_state(project.root)
    project.write("api/src/x.py", "def f() -> int:\n    return 1\n")
    return review.brief(project.root)


def test_brief_lists_tree_principles_decisions_and_diff(project: Project) -> None:
    text = briefed(project)
    head, rest = text.split("\n", 1)
    assert head == f"Tree: {review.snapshot(project.root)}"
    assert rest.startswith("Reviewed: ")
    principles = text.split("## Principles\n")[1].split("\n## ")[0]
    assert "- fail-helpfully (Fail fast, fail helpfully): " in principles
    assert (
        "- observability " in principles and "override: docs/decisions/" in principles
    )
    decisions = text.split("## Decisions\n")[1].split("\n## ")[0]
    assert "- 0001 Use OpenAPI (docs/decisions/0001-use-openapi.md)" in decisions
    files = text.split("## Changed files\n")[1].split("\n## ")[0]
    assert files.strip() == "2\tapi/src/x.py"
    assert "+def f() -> int:" in text.split("## Diff\n")[1]


def test_brief_omits_principles_of_untouched_components(project: Project) -> None:
    principles = briefed(project).split("## Principles\n")[1].split("\n## ")[0]
    assert "visual-system" not in principles
    assert "- contracts " in principles


def test_brief_lists_the_stack_rules_of_touched_components(project: Project) -> None:
    rules = briefed(project).split("## Stack rules\n")[1].split("\n## ")[0]
    assert rules.strip().splitlines() == [
        "- python:uv-for-dependencies: Add and remove dependencies with `uv add` "
        "and `uv remove`, never by editing the dependency lists in "
        "`pyproject.toml` or with `pip`. [components: api]",
        "- python:typed-boundaries: Parse external input (JSON, files, "
        "environment, requests) into dataclasses or typed models at the "
        "boundary; don't pass `dict[str, Any]` inward. [components: api]",
        "- python:import-contracts: Once a component has more than one package, "
        "add import-linter contracts for the layers `docs/architecture.md` "
        "names, and add `lint-imports` to its `structure` command. "
        "[components: api]",
    ]


def test_brief_lists_every_stacks_rules_for_a_change_outside_components(
    project: Project,
) -> None:
    review.ensure_state(project.root)
    project.write("notes.txt", "x\n")
    rules = review.brief(project.root).split("## Stack rules\n")[1].split("\n## ")[0]
    ids = [line.split(": ")[0] for line in rules.strip().splitlines()]
    assert ids == [
        "- python:uv-for-dependencies",
        "- python:typed-boundaries",
        "- python:import-contracts",
        "- typescript:top-level-imports",
        "- typescript:unknown-at-boundaries",
        "- typescript:pnpm-for-dependencies",
    ]


def test_brief_has_no_stack_rules_section_without_rules(project: Project) -> None:
    data = project.principles()
    for comp in data["components"]:
        comp["rules"] = []
    project.write_principles(data)
    assert "## Stack rules" not in briefed(project)


def test_brief_skips_superseded_decisions(project: Project) -> None:
    decisions = briefed(project).split("## Decisions\n")[1].split("\n## ")[0]
    assert "Use REST" not in decisions and "Use gRPC" in decisions


def test_brief_lists_open_findings(project: Project) -> None:
    briefed(project)
    state = review.load_state(project.root)
    state["findings"] = [
        {
            "id": "F-abc123",
            "principle": "timeouts",
            "file": "api/src/x.py",
            "line": 1,
            "problem": "no timeout",
            "fix": "add one",
            "accepted": False,
        }
    ]
    review.save_state(project.root, state)
    text = review.brief(project.root)
    assert "## Open findings\n\n- F-abc123 timeouts api/src/x.py:1: no timeout" in text


def test_brief_truncates_long_diffs_and_names_the_rest(project: Project) -> None:
    briefed(project)
    project.write("api/src/big.py", lines(2000))
    project.write("web/src/z.ts", "export {}\n")
    text = review.brief(project.root)
    diff = text.split("## Diff\n")[1]
    assert len(diff.splitlines()) <= review.DIFF_LINES + 2
    tail = diff.splitlines()[-1]
    assert tail.startswith("… diff truncated; read the remaining files directly: ")
    assert "api/src/big.py" in tail and "web/src/z.ts" in tail


def test_brief_leaves_lockfile_diffs_out(project: Project) -> None:
    briefed(project)
    project.write("api/uv.lock", lines(3000))
    text = review.brief(project.root)
    files = text.split("## Changed files\n")[1].split("\n## ")[0]
    assert "api/uv.lock" in files
    diff = text.split("## Diff\n")[1]
    assert "diff --git a/api/uv.lock" not in diff
    assert "+def f() -> int:" in diff
    assert "Lockfiles changed (diff left out): api/uv.lock" in diff
    assert "truncated" not in diff


def test_brief_names_non_ascii_files_as_they_are(project: Project) -> None:
    briefed(project)
    project.write("api/src/café.py", lines(2000))
    diff = review.brief(project.root).split("## Diff\n")[1]
    assert "diff --git a/api/src/café.py b/api/src/café.py" in diff
    tail = diff.splitlines()[-1]
    assert "api/src/café.py" in tail and '"' not in tail


@pytest.mark.parametrize(
    "finding",
    [
        "F-abc123",
        {"id": "F-abc123"},
        {"id": 1, "principle": "p", "file": "f", "line": 1, "problem": "x", "fix": "y"},
    ],
)
def test_malformed_findings_restart_the_review(
    project: Project, finding: object
) -> None:
    base(project)
    path = project.root / ".claude/alpha/state/review.json"
    state = review.ensure_state(project.root)
    state["findings"] = [finding]
    path.write_text(json.dumps(state))
    assert review.load_state(project.root) == {"unreadable": True}
    review.gate(project.root, project.principles())
    assert review.ensure_state(project.root)["findings"] == []


def test_brief_cli_outside_an_alpha_project(project: Project) -> None:
    (project.root / "docs/principles.toml").unlink()
    proc = project.run_hook("review.py", {})
    assert proc.returncode == 1
    assert "python3 .claude/alpha/hooks/review.py brief" in proc.stderr


def test_absorb_carries_changes_since_the_tree_onto_reviewed(
    project: Project,
) -> None:
    base(project)
    before = review.snapshot(project.root)
    project.write("api/src/from_alpha.py", "x = 1\n")
    after = review.snapshot(project.root)
    assert review.absorb(project.root, before, after) is True
    assert review.debt(project.root, project.principles())["files"] == []


def test_absorb_keeps_earlier_unreviewed_edits(project: Project) -> None:
    base(project)
    project.write("api/src/mine.py", "x = 1\n")
    before = review.snapshot(project.root)
    project.write("api/src/from_alpha.py", "y = 2\n")
    after = review.snapshot(project.root)
    review.absorb(project.root, before, after)
    debt = review.debt(project.root, project.principles())
    assert debt["files"] == ["api/src/mine.py"]


def test_absorb_stops_at_the_after_tree(project: Project) -> None:
    base(project)
    before = review.snapshot(project.root)
    project.write("api/src/from_alpha.py", "y = 2\n")
    after = review.snapshot(project.root)
    project.write("api/src/later.py", "z = 3\n")
    review.absorb(project.root, before, after)
    debt = review.debt(project.root, project.principles())
    assert debt["files"] == ["api/src/later.py"]


def test_absorb_carries_per_path_on_a_conflict(project: Project) -> None:
    project.write("api/src/clash.py", "a = 1\nb = 2\nc = 3\n")
    base(project)
    project.write("api/src/clash.py", "a = 1\nb = 'mine'\nc = 3\n")
    before = review.snapshot(project.root)
    project.write("api/src/clash.py", "a = 1\nb = 'alpha'\nc = 3\n")
    project.write("api/src/other.py", "o = 1\n")
    after = review.snapshot(project.root)
    proc = subprocess.run(
        [sys.executable, str(HOOKS / "review.py"), "absorb", before, after],
        cwd=project.root,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project.root)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    debt = review.debt(project.root, project.principles())
    assert debt["files"] == ["api/src/clash.py"]


def test_snapshot_subcommand_prints_the_tree(project: Project) -> None:
    base(project)
    project.write("api/src/new.py", "x = 1\n")
    proc = subprocess.run(
        [sys.executable, str(HOOKS / "review.py"), "snapshot"],
        cwd=project.root,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project.root)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == review.snapshot(project.root)


def test_snapshot_works_when_the_state_folder_is_gitignored(project: Project) -> None:
    project.write(".gitignore", ".claude/alpha/state/\n")
    base(project)
    project.write("api/src/new.py", "x = 1\n")
    debt = review.debt(project.root, project.principles())
    assert debt["files"] == ["api/src/new.py"]
    assert debt["tree"] != tree_of(project, "HEAD")


def test_brief_refuses_when_the_tree_cannot_be_snapshot(project: Project) -> None:
    base(project)
    (project.root / ".git").rename(project.root / "not-git")
    proc = subprocess.run(
        [sys.executable, str(HOOKS / "review.py"), "brief"],
        cwd=project.root,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project.root)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "can't snapshot the working tree" in proc.stderr


def scratch_index(project: Project) -> Any:
    return project.root / ".git" / review.INDEX_FILE


def test_scratch_index_persists_and_snapshots_agree(project: Project) -> None:
    base(project)
    project.write("api/src/x.py", "x = 1\n")
    first = review.snapshot(project.root)
    assert scratch_index(project).is_file()
    assert review.snapshot(project.root) == first


def test_a_stale_lock_is_cleared(project: Project) -> None:
    base(project)
    lock = scratch_index(project).with_name(review.INDEX_FILE + ".lock")
    lock.write_text("")
    old = time.time() - 600
    os.utime(lock, (old, old))
    project.write("api/src/x.py", "x = 1\n")
    assert review.debt(project.root, project.principles())["files"] == ["api/src/x.py"]


def test_a_fresh_lock_fails_loudly(project: Project) -> None:
    base(project)
    lock = scratch_index(project).with_name(review.INDEX_FILE + ".lock")
    lock.write_text("")
    with pytest.raises(review.SnapshotError, match="lock"):
        review.debt(project.root, project.principles())
    reason = review.push_blocker(project.root, project.principles())
    assert reason is not None
    assert reason.startswith("Nothing leaves the machine unreviewed, but alpha can't")
    assert "push by hand" in reason


def test_an_unreadable_file_fails_loudly(project: Project) -> None:
    base(project)
    secret = project.write("api/src/locked.py", "x = 1\n")
    secret.chmod(0)
    try:
        with pytest.raises(review.SnapshotError):
            review.snapshot(project.root)
    finally:
        secret.chmod(0o644)


def test_lost_state_starts_at_the_pushed_commit(
    project: Project, tmp_path_factory: Any
) -> None:
    remote = tmp_path_factory.mktemp("remote")
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    base(project)
    project.git("remote", "add", "origin", str(remote))
    project.git("push", "-q", "-u", "origin", "HEAD")
    project.write("api/auth/login.py", "x = 1\n")
    commit_all(project, "feat: Add login")
    (project.root / ".claude/alpha/state/review.json").unlink()
    debt = review.debt(project.root, project.principles())
    assert debt["files"] == ["api/auth/login.py"]


def test_state_is_written_atomically(project: Project) -> None:
    base(project)
    state = review.load_state(project.root)
    review.save_state(project.root, state)
    leftovers = [p.name for p in (project.root / ".claude/alpha/state").iterdir()]
    assert not [n for n in leftovers if n.startswith("review.json.")]


def test_unreadable_state_is_reported_at_session_start(project: Project) -> None:
    base(project)
    (project.root / ".claude/alpha/state/review.json").write_text("{not json")
    out = project.run_hook("session_start.py", {"hook_event_name": "SessionStart"})
    text = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "review state was unreadable" in text


def test_brief_shows_the_touched_components_params(project: Project) -> None:
    principles = briefed(project).split("## Principles\n")[1].split("\n## ")[0]
    line = next(x for x in principles.splitlines() if x.startswith("- perf-budgets "))
    assert (
        "[api: budgets=['p95 response time: 300 ms (k6 in CI against staging)']]"
        in (line)
    )
    assert "web:" not in line


def test_brief_shows_the_tokens_of_a_touched_ui(project: Project) -> None:
    project.write("web/package.json", "{}\n")
    commit_all(project)
    review.ensure_state(project.root)
    project.write("web/src/app.ts", "export const x = 1;\n")
    principles = review.brief(project.root).split("## Principles\n")[1]
    line = next(x for x in principles.splitlines() if x.startswith("- visual-system "))
    assert "[web: tokens=web/src/styles/tokens.css]" in line
