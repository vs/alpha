"""Adopted recipes (spec §5b, A1): a repo's own tools, as a recipe."""

import copy
from typing import Any

import pytest
from helpers import proven, shell_recipe

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
