import json
import re
from pathlib import Path
from typing import Any

import pytest
from helpers import SCENARIOS, TODAY, proven, shell_recipe, single_component
from test_defaults import make_source

from alpha import cli, toml_write
from alpha.answers import AnswersError, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import DefaultsError, Source
from alpha.generate import generate, project_book
from alpha.recipe_cli import save_recipe
from alpha.recipes import RecipeBook, RecipeError, recipe_hash


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


def test_try_finds_the_missing_tool_after_cd(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    recipe = shell_recipe()
    recipe["commands"]["setup"] = "cd . && no-such-tool-xyz sync"
    target = project(tmp_path, recipe)
    assert cli.main(["recipe", "try", str(target), "shell"]) == 1
    err = capsys.readouterr().err
    assert "no-such-tool-xyz wasn't found: install no-such-tool-xyz" in err
    assert "package manager" in err


def test_try_stops_a_command_that_hangs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("alpha.recipe_cli._TIMEOUT_SECONDS", 0.5)
    recipe = shell_recipe()
    recipe["commands"]["setup"] = "sh -c 'sleep 5'"
    target = project(tmp_path, recipe)
    assert cli.main(["recipe", "try", str(target), "shell"]) == 1
    err = capsys.readouterr().err
    assert "took longer than 0.5s" in err
    assert "waits for input" in err


def scenario_with_shell(target: Path, recipe: dict[str, Any]) -> None:
    data = json.loads((SCENARIOS / "python-ml-single.json").read_text())
    single_component(data, dict(data["components"][0], stack="shell"))
    data["recipes"] = {"shell": recipe}
    path = target / ".claude/alpha/project.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_an_unproven_recipe_is_refused(tmp_path: Path):
    """R6: a drafted recipe is refused until alpha recipe try proves it."""
    scenario_with_shell(tmp_path, shell_recipe())
    with pytest.raises(
        AnswersError, match=r"recipes\.shell: not proven.*alpha recipe try"
    ):
        generate(tmp_path, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), 2026, TODAY)


def test_a_recipe_edited_after_try_is_refused(tmp_path: Path):
    """R6: an edit after the proof makes the recipe unproven again."""
    recipe = shell_recipe()
    recipe["proven_hash"] = recipe_hash(recipe)
    recipe["commands"]["lint"] = "true"
    scenario_with_shell(tmp_path, recipe)
    with pytest.raises(AnswersError, match=r"not proven since it last changed"):
        generate(tmp_path, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), 2026, TODAY)


def drafted_project(tmp_path: Path, recipe: dict[str, Any]) -> Path:
    target = project(tmp_path, recipe)
    path = target / ".claude/alpha/project.json"
    data = json.loads(path.read_text())
    data["identity"] = {"slug": "leaf-lens"}
    path.write_text(json.dumps(data))
    return target


def saving_to(src: Source, monkeypatch: pytest.MonkeyPatch) -> Path:
    assert src.user is not None
    monkeypatch.setenv("ALPHA_CONFIG_DIR", str(src.user))
    return src.user / "recipes"


def test_save_writes_the_recipe_to_your_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    src = make_source(tmp_path / "src")
    folder = saving_to(src, monkeypatch)
    target = drafted_project(tmp_path / "p", proven(shell_recipe()))
    assert save_recipe(target, "shell", src) == folder / "shell.toml"
    assert (
        (folder / "shell.toml")
        .read_text()
        .startswith("# Drafted in the leaf-lens interview and proven there;")
    )
    saved = RecipeBook().get("shell")
    assert saved.proven is False
    assert saved.templates == shell_recipe()["templates"]
    assert saved.commands == {**shell_recipe()["commands"], "structure": ""}
    assert not (src.path / "recipes").exists()


def test_save_keeps_templates_whose_flat_names_would_collide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    src = make_source(tmp_path / "src")
    saving_to(src, monkeypatch)
    recipe = shell_recipe()
    recipe["templates"]["tests-setup.sh"] = "echo flat\n"
    target = drafted_project(tmp_path / "p", proven(recipe))
    save_recipe(target, "shell", src)
    saved = RecipeBook().get("shell").templates
    assert saved["tests/setup.sh"] == "test 1 -eq 1\n"
    assert saved["tests-setup.sh"] == "echo flat\n"


def test_save_needs_a_folder_for_your_recipes(tmp_path: Path):
    target = drafted_project(tmp_path, proven(shell_recipe()))
    with pytest.raises(DefaultsError, match="ALPHA_CONFIG_DIR"):
        save_recipe(target, "shell", Source(tmp_path / "plugin", False))


def test_save_refuses_an_unproven_recipe(tmp_path: Path):
    src = make_source(tmp_path / "src")
    target = drafted_project(tmp_path / "p", shell_recipe())
    with pytest.raises(AnswersError, match="not proven"):
        save_recipe(target, "shell", src)


def test_save_refuses_a_recipe_you_already_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    src = make_source(tmp_path / "src")
    folder = saving_to(src, monkeypatch)
    target = drafted_project(tmp_path / "p", proven(shell_recipe()))
    save_recipe(target, "shell", src)
    with pytest.raises(AnswersError, match="already has a shell recipe"):
        save_recipe(target, "shell", src)
    (folder / "shell.toml").unlink()
    with pytest.raises(AnswersError, match="you already saved a shell recipe"):
        save_recipe(target, "shell", src)


def test_save_refuses_a_stack_the_kit_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    src = make_source(tmp_path / "src")
    saving_to(src, monkeypatch)
    (src.path / "recipes").mkdir()
    (src.path / "recipes/shell.toml").write_text('stack = "shell"\n')
    monkeypatch.setenv("ALPHA_SOURCE", str(src.path))
    target = drafted_project(tmp_path / "p", proven(shell_recipe()))
    with pytest.raises(AnswersError, match="the kit already has a shell recipe"):
        save_recipe(target, "shell", src)


def test_save_leaves_nothing_when_a_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    src = make_source(tmp_path / "src")
    folder = saving_to(src, monkeypatch)
    target = drafted_project(tmp_path / "p", proven(shell_recipe()))
    write = Path.write_text

    def full_disk(self: Path, *args: Any, **kwargs: Any) -> int:
        if self.suffix == ".toml" and self.parent == folder:
            raise OSError(28, "No space left on device", str(self))
        return write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", full_disk)
    assert cli.main(["recipe", "save", str(target), "shell"]) == 3
    assert "No space left on device" in capsys.readouterr().err
    assert not (folder / "shell").exists()
    assert not (folder / "shell.toml").exists()


def test_cli_save_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    target = drafted_project(tmp_path / "p", proven(shell_recipe()))
    monkeypatch.setenv("ALPHA_SOURCE", str(tmp_path / "missing"))
    assert cli.main(["recipe", "save", str(target), "shell"]) == 3
    assert "unset it to use the installed plugin" in capsys.readouterr().err
    monkeypatch.delenv("ALPHA_SOURCE")
    monkeypatch.setenv("ALPHA_CONFIG_DIR", str(tmp_path / "config"))
    assert cli.main(["recipe", "save", str(target), "shell"]) == 0
    saved = tmp_path / "config/recipes/shell.toml"
    assert capsys.readouterr().out == (
        f"saved: shell recipe in {saved}; new projects can use it\n"
    )


def broken_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    src = make_source(tmp_path / "src")
    folder = src.path / "recipes"
    folder.mkdir()
    (folder / "bad.toml").write_text("x = [\n")
    gone = {k: v for k, v in shell_recipe().items() if k != "templates"}
    gone["files"] = {"tests/setup.sh": "setup.sh.tmpl"}
    (folder / "gone.toml").write_text(toml_write.dumps(gone))
    monkeypatch.setenv("ALPHA_SOURCE", str(src.path))
    return folder


def test_a_broken_kit_recipe_is_named_with_its_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    folder = broken_source(tmp_path, monkeypatch)
    with pytest.raises(RecipeError, match=rf"{re.escape(str(folder))}/bad.toml"):
        RecipeBook().get("bad")
    with pytest.raises(RecipeError, match=r"gone\.toml.*setup\.sh\.tmpl"):
        RecipeBook().get("gone")


def test_list_keeps_going_past_a_broken_recipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    broken_source(tmp_path, monkeypatch)
    assert cli.main(["recipe", "list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "python (proven)" in lines
    assert any(line.startswith("bad (broken: ") for line in lines)
    assert any(line.startswith("gone (broken: ") for line in lines)


def test_saving_a_recipe_keeps_its_project_working(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    src = make_source(tmp_path / "src")
    saving_to(src, monkeypatch)
    target = tmp_path / "proj"
    scenario_with_shell(target, proven(shell_recipe()))
    generate(target, PLUGIN_ROOT, Source(PLUGIN_ROOT, True), 2026, TODAY)
    save_recipe(target, "shell", src)
    answers = load_answers(target / ".claude/alpha/project.json")
    assert answers.book().get("shell").proven is False
    assert project_book(target).get("shell").templates == shell_recipe()["templates"]


def test_save_writes_nothing_when_the_toml_cannot_be_rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    src = make_source(tmp_path / "src")
    folder = saving_to(src, monkeypatch)
    target = drafted_project(tmp_path / "p", proven(shell_recipe()))

    def fail(_: object) -> str:
        raise TypeError("cannot write <class 'float'> at ci.steps")

    monkeypatch.setattr(toml_write, "dumps", fail)
    with pytest.raises(AnswersError, match="can't be written as TOML"):
        save_recipe(target, "shell", src)
    assert not folder.exists()


def test_try_fails_when_commands_create_source_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    recipe = shell_recipe()
    recipe["commands"]["setup"] = "mkdir -p src && touch src/app.sh"
    target = project(tmp_path, recipe)
    assert cli.main(["recipe", "try", str(target), "shell"]) == 1
    err = capsys.readouterr().err
    assert "created source files (src/app.sh)" in err
    assert "no app code" in err
    assert "proven_hash" not in recipes_of(target)["shell"]


def _baselined(command: str) -> dict[str, Any]:
    recipe = shell_recipe()
    recipe["commands"]["lint"] = "true"
    recipe["baseline"] = {
        "lint": {"command": command, "pattern": r"^(?P<file>\S+):\d+: (?P<rule>E\d+)"}
    }
    return recipe


def test_try_proves_a_baseline_reader(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    target = project(tmp_path, _baselined("echo 'All clean, 0 findings'"))
    assert cli.main(["recipe", "try", str(target), "shell"]) == 0


def test_try_refuses_a_baseline_that_reads_findings_on_the_skeleton(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    target = project(tmp_path, _baselined("echo 'summary.txt:0: E0 found 0'"))
    assert cli.main(["recipe", "try", str(target), "shell"]) == 1
    err = capsys.readouterr().err
    assert "reads findings on the clean skeleton" in err and "summary.txt:0" in err
    assert "proven_hash" not in recipes_of(target)["shell"]


def test_try_refuses_a_failing_baseline_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    target = project(tmp_path, _baselined("sh -c 'echo crashed; exit 4'"))
    assert cli.main(["recipe", "try", str(target), "shell"]) == 1
    err = capsys.readouterr().err
    assert "failed (exit 4) on the clean skeleton" in err and "crashed" in err


def test_try_refuses_unreadable_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    recipe = _baselined("echo nope")
    recipe["baseline"]["lint"] = {
        "command": "echo nope",
        "json": {"items": "diagnostics.*", "file": "file"},
    }
    target = project(tmp_path, recipe)
    assert cli.main(["recipe", "try", str(target), "shell"]) == 1
    assert "isn't JSON" in capsys.readouterr().err
