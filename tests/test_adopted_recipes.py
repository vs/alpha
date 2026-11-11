"""Adopted recipes (spec §5b, A1): a repo's own tools, as a recipe."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from helpers import git, proven, run_cli, shell_recipe

from alpha import recipe_cli
from alpha.answers import AnswersError, drafted_recipes
from alpha.recipes import RecipeBook, recipe_hash

KIT = RecipeBook().data("python")


def adopted(**fields: Any) -> dict[str, Any]:
    return {"adopted": True, "extends": "python", **fields}


def load(entry: dict[str, Any], name: str = "api-python") -> Any:
    return drafted_recipes({name: entry})[name]


def test_adopted_needs_its_own_name():
    with pytest.raises(AnswersError, match='e.g. "api-python"'):
        load(adopted(), name="python")


def test_adopted_may_have_no_templates():
    raw = shell_recipe()
    raw["templates"] = {}
    with pytest.raises(AnswersError, match="templates: is empty"):
        load(raw, "sh")
    recipe = load({**raw, "adopted": True}, "sh")
    assert recipe.adopted and recipe.templates == {}


def test_adopted_bootstrap_must_be_empty():
    raw = {**shell_recipe(), "adopted": True, "bootstrap": ["pip install x"]}
    with pytest.raises(AnswersError, match="doesn't install tools") as e:
        load(raw, "sh")
    assert "step of the adoption plan" in str(e.value)


def test_adopted_test_may_be_empty():
    raw = copy.deepcopy(shell_recipe())
    raw["commands"]["test"] = ""
    raw["allow"] = []  # its rule named the test command's tool
    with pytest.raises(AnswersError, match=r"commands\.test: is empty"):
        load(raw, "sh")
    assert load({**raw, "adopted": True}, "sh").commands["test"] == ""
    raw["commands"]["setup"] = ""
    with pytest.raises(AnswersError, match=r"commands\.setup: is empty"):
        load({**raw, "adopted": True}, "sh")


def test_extends_fills_from_the_kit():
    recipe = load(adopted())
    kit = RecipeBook().get("python")
    assert recipe.commands == kit.commands
    assert recipe.rules == kit.rules and recipe.ignores == kit.ignores
    assert recipe.lockfiles == kit.lockfiles and recipe.ci == kit.ci
    assert set(recipe.baselines) == set(kit.baselines)
    # Nothing that installs or writes into the repo comes along.
    assert recipe.bootstrap == [] and recipe.templates == {} and recipe.why == {}
    assert recipe.coverage == ""


def test_extends_drops_readers_of_changed_steps():
    recipe = load(adopted(commands={"typecheck": "uv run mypy ."}))
    assert recipe.commands["typecheck"] == "uv run mypy ."
    assert recipe.commands["lint"] == KIT["commands"]["lint"]
    assert "typecheck" not in recipe.baselines and "lint" in recipe.baselines
    own = {
        "command": "uv run mypy .",
        "pattern": r"^(?P<file>[^:]+):\d+: error: .*\[(?P<rule>[\w-]+)\]$",
    }
    recipe = load(
        adopted(commands={"typecheck": "uv run mypy ."}, baseline={"typecheck": own})
    )
    assert recipe.baselines["typecheck"].command == "uv run mypy ."


def test_changed_lint_file_needs_its_own_file_command():
    entry = adopted(commands={"lint_file": "uv run ruff check --select E {file}"})
    with pytest.raises(AnswersError, match=r"baseline\.lint\.file_command: is missing"):
        load(entry)


def test_extends_unknown_stack():
    with pytest.raises(AnswersError, match=r"extends: 'cobol' isn't a kit recipe") as e:
        load(adopted(extends="cobol"))
    assert "python" in str(e.value)


def test_extends_needs_adopted():
    entry = {**shell_recipe(), "extends": "python"}
    with pytest.raises(AnswersError, match="isn't adopted"):
        load(entry, "sh")


def test_adopted_hash_covers_the_entry():
    entry = adopted(commands={"typecheck": "uv run mypy ."})
    drafted_recipes({"api-python": proven(entry)}, require_proven=True)
    changed = {**proven(entry), "extends": "typescript"}
    assert recipe_hash(changed) != changed["proven_hash"]
    with pytest.raises(AnswersError, match="not proven since it last changed"):
        drafted_recipes({"api-python": changed}, require_proven=True)


# --- proving an adopted recipe on the repo (alpha recipe try) ---

READER = r"^(?P<file>[^:\s]+):\d+: (?P<rule>E\d+)"


def _repo_with(tmp_path: Path, commands: dict[str, str], **extra: Any) -> Path:
    root = tmp_path / "repo"
    (root / "svc").mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "svc" / "app.txt").write_text("committed\n")
    (root / "svc" / "findings.txt").write_text("a.py:1: E1\na.py:2: E1\nb.py:1: E2\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "feat: Start")
    recipe = {**shell_recipe(), "adopted": True, "templates": {}, "allow": []}
    recipe["commands"] = {**recipe["commands"], "test": "true", **commands}
    recipe.update(extra)
    project = root / ".claude/alpha/project.json"
    project.parent.mkdir(parents=True)
    components = [{"name": "svc", "path": "svc", "stack": "svc-sh"}]
    project.write_text(
        json.dumps({"components": components, "recipes": {"svc-sh": recipe}})
    )
    return root


def _try(root: Path, report: list[str] | None = None) -> str | None:
    return recipe_cli.try_recipe(root, "svc-sh", report)


def _worktrees(root: Path) -> int:
    return len(git(root, "worktree", "list").splitlines())


def test_try_adopted_proves_on_head(tmp_path: Path, git_env: None):
    root = _repo_with(tmp_path, {"lint": "grep -q committed app.txt"})
    (root / "svc" / "app.txt").write_text("edited\n")  # not committed: not seen
    report: list[str] = []
    assert _try(root, report) is None
    assert report[0].startswith("on svc at ")
    saved = json.loads((root / ".claude/alpha/project.json").read_text())
    assert "proven_hash" in saved["recipes"]["svc-sh"]
    assert (root / "svc" / "app.txt").read_text() == "edited\n"


def test_try_adopted_reports_legacy_findings(tmp_path: Path, git_env: None):
    reader = {"command": "cat findings.txt", "pattern": READER}
    root = _repo_with(tmp_path, {"lint": "false"}, baseline={"lint": reader})
    report: list[str] = []
    assert _try(root, report) is None
    assert report[1:] == ["svc: lint: 3 findings in 2 files"]
    done = run_cli("recipe", "try", str(root), "svc-sh")
    assert done.returncode == 0, done.stderr
    assert "svc: lint: 3 findings in 2 files (to baseline)" in done.stdout


def test_try_adopted_unreadable_failure(tmp_path: Path, git_env: None):
    reader = {"command": "echo crashed", "pattern": READER}
    root = _repo_with(tmp_path, {"lint": "false"}, baseline={"lint": reader})
    problem = _try(root)
    assert problem is not None and "reads no findings" in problem
    reader = {"command": "echo crashed", "json": {"items": "x.*", "file": "f"}}
    root = _repo_with(tmp_path / "j", {"lint": "false"}, baseline={"lint": reader})
    problem = _try(root)
    assert problem is not None and "isn't JSON" in problem


def test_try_adopted_failing_check_without_a_reader(tmp_path: Path, git_env: None):
    root = _repo_with(tmp_path, {"typecheck": "sh -c 'echo nope; exit 2'"})
    problem = _try(root)
    assert problem is not None
    assert "Add [baseline.typecheck]" in problem and "nope" in problem


def test_try_adopted_unformatted(tmp_path: Path, git_env: None):
    root = _repo_with(tmp_path, {"format_check": "false"})
    problem = _try(root)
    assert problem is not None and 'commands.format_check to ""' in problem


def test_try_adopted_needs_a_component(tmp_path: Path, git_env: None):
    root = _repo_with(tmp_path, {})
    project = root / ".claude/alpha/project.json"
    data = json.loads(project.read_text())
    data["components"] = []
    project.write_text(json.dumps(data))
    problem = _try(root)
    assert problem is not None and "No component uses the svc-sh recipe" in problem


def test_try_adopted_removes_its_worktree(
    tmp_path: Path, git_env: None, monkeypatch: pytest.MonkeyPatch
):
    ok = _repo_with(tmp_path / "ok", {})
    assert _try(ok) is None and _worktrees(ok) == 1
    failing = _repo_with(tmp_path / "fail", {"lint": "false"})
    assert _try(failing) is not None and _worktrees(failing) == 1
    monkeypatch.setattr(recipe_cli, "_TIMEOUT_SECONDS", 0.5)
    slow = _repo_with(tmp_path / "slow", {"lint": "sleep 5"})
    problem = _try(slow)
    assert problem is not None and "took longer than" in problem
    assert _worktrees(slow) == 1
