import json
from typing import Any

import review

from .conftest import Project


def commit_all(project: Project, message: str = "chore: Base") -> None:
    project.git("add", "-A")
    project.git("commit", "-q", "--allow-empty", "-m", message)


def base(project: Project) -> dict[str, Any]:
    """Components exist and are committed, as in a generated project."""
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
    project.write(".gitignore", "*.log\n")
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
    assert debt["counted_lines"] == 3 + 2  # one line removed, one added
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
    commit_all(project)  # web/ doesn't exist yet
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
    assert review.load_state(project.root) == {}
    assert review.ensure_state(project.root)["reviewed_tree"] == tree_of(
        project, "HEAD"
    )
    assert json.loads(path.read_text())["findings"] == []
