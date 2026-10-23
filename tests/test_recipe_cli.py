import json
from pathlib import Path
from typing import Any

import pytest
from helpers import SCENARIOS, TODAY, shell_recipe, single_component

from alpha import cli
from alpha.answers import AnswersError
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import generate
from alpha.recipes import recipe_hash


def project(tmp_path: Path, recipe: dict[str, Any] | None = None) -> Path:
    path = tmp_path / ".claude/alpha/project.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"recipes": {"shell": recipe or shell_recipe()}}))
    return tmp_path


def recipes_of(target: Path) -> dict[str, Any]:
    return json.loads((target / ".claude/alpha/project.json").read_text())["recipes"]


def test_list_shows_the_kit_stacks(capsys: pytest.CaptureFixture[str]):
    assert cli.main(["recipe", "list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "python (proven)" in lines and "typescript (proven)" in lines


def test_check_ok_and_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    target = project(tmp_path)
    assert cli.main(["recipe", "check", str(target), "shell"]) == 0
    assert capsys.readouterr().out.strip() == "ok"
    bad = shell_recipe()
    bad["commands"]["test"] = ""
    target = project(tmp_path / "bad", bad)
    assert cli.main(["recipe", "check", str(target), "shell"]) == 1
    assert "recipes.shell.commands.test" in capsys.readouterr().err


def test_check_unknown_stack(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    target = project(tmp_path)
    assert cli.main(["recipe", "check", str(target), "rust"]) == 1
    assert 'no drafted recipe for "rust"' in capsys.readouterr().err


def test_try_proves_the_recipe(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    target = project(tmp_path)
    assert cli.main(["recipe", "try", str(target), "shell"]) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "ok: shell recipe proven"
    assert "alpha: try: sh tests/setup.sh" in out.err
    saved = recipes_of(target)["shell"]
    assert saved["proven_hash"] == recipe_hash(saved)


def leftovers(tmp_path: Path) -> list[str]:
    return [p.name for p in Path(tmp_path).glob("alpha-try-*")]


def test_try_failure_names_the_command_and_cleans_up(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    recipe = shell_recipe()
    recipe["commands"]["lint"] = "sh -c 'echo bad style; exit 3'"
    target = project(tmp_path / "p", recipe)
    assert cli.main(["recipe", "try", str(target), "shell"]) == 1
    err = capsys.readouterr().err
    assert "sh -c 'echo bad style; exit 3'" in err and "bad style" in err
    assert "Fix the recipe's lint command" in err
    assert "proven_hash" not in recipes_of(target)["shell"]
    assert leftovers(tmp_path) == []


def test_try_says_to_install_a_missing_tool(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    recipe = shell_recipe()
    recipe["commands"]["setup"] = "no-such-tool-xyz sync"
    target = project(tmp_path, recipe)
    assert cli.main(["recipe", "try", str(target), "shell"]) == 1
    assert "install no-such-tool-xyz" in capsys.readouterr().err


def scenario_with_shell(target: Path, recipe: dict[str, Any]) -> None:
    data = json.loads((SCENARIOS / "python-ml-single.json").read_text())
    single_component(data, dict(data["components"][0], stack="shell"))
    data["recipes"] = {"shell": recipe}
    path = target / ".claude/alpha/project.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_an_unproven_recipe_is_refused(tmp_path: Path):
    scenario_with_shell(tmp_path, shell_recipe())
    with pytest.raises(
        AnswersError, match=r"recipes\.shell: not proven.*alpha recipe try"
    ):
        generate(tmp_path, PLUGIN_ROOT, Source(PLUGIN_ROOT, True, ""), 2026, TODAY)


def test_a_recipe_edited_after_try_is_refused(tmp_path: Path):
    recipe = shell_recipe()
    recipe["proven_hash"] = recipe_hash(recipe)
    recipe["commands"]["lint"] = "true"  # changed after it was proven
    scenario_with_shell(tmp_path, recipe)
    with pytest.raises(AnswersError, match=r"not proven since it last changed"):
        generate(tmp_path, PLUGIN_ROOT, Source(PLUGIN_ROOT, True, ""), 2026, TODAY)
