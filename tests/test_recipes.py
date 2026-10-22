import json
import re
import tomllib

import pytest

from alpha.answers import Component, Traits
from alpha.cli import PLUGIN_ROOT
from alpha.recipes import CHECK_STEPS, check_commands, load_recipe, render_component


def _component(stack: str, kind: str, name: str, path: str) -> Component:
    traits = Traits(False, False, False, False, False, False)
    return Component(name=name, path=path, kind=kind, stack=stack, traits=traits)


def py_component(name: str = "api", path: str = "api") -> Component:
    return _component("python", "backend", name, path)


def ts_component(name: str = "web", path: str = "web") -> Component:
    return _component("typescript", "frontend", name, path)


def test_python_component_files():
    files = render_component(py_component(path="api"), "pico")
    assert set(files) == {
        "api/pyproject.toml",
        "api/tests/test_setup.py",
        "api/.python-version",
    }
    assert files["api/.python-version"] == "3.12\n"
    pp = tomllib.loads(files["api/pyproject.toml"])
    assert pp["tool"]["pyright"]["typeCheckingMode"] == "strict"
    assert pp["project"]["name"] == "pico-api"
    assert pp["tool"]["uv"]["package"] is False


def test_typescript_component_files():
    files = render_component(ts_component(path="web"), "pico")
    assert set(files) == {
        "web/package.json",
        "web/tsconfig.json",
        "web/biome.json",
        "web/tests/setup.test.ts",
        "web/.node-version",
    }
    assert files["web/.node-version"] == "26\n"
    tsc = json.loads(files["web/tsconfig.json"])
    assert tsc["compilerOptions"]["strict"] is True
    pkg = json.loads(files["web/package.json"])
    assert pkg["type"] == "module" and pkg["name"] == "pico-web"
    biome = json.loads(files["web/biome.json"])
    # Biome formats YAML since 2.6; the lockfile changes only through pnpm.
    for lockfile in load_recipe("typescript").lockfiles:
        assert f"!**/{lockfile}" in biome["files"]["includes"]
    # A root component would otherwise reformat alpha's own files and the
    # Markdown docs, whose tables Biome (2.6+) aligns.
    assert "!**/.claude" in biome["files"]["includes"]
    assert "!**/*.md" in biome["files"]["includes"]


def test_single_layout_path_dot():
    files = render_component(py_component(path="."), "pico")
    assert set(files) == {"pyproject.toml", "tests/test_setup.py", ".python-version"}


def test_command_keys_complete():
    for s in ("python", "typescript"):
        assert set(load_recipe(s).commands) == {
            "setup",
            "test",
            "lint",
            "format",
            "format_check",
            "typecheck",
            "format_file",
            "lint_file",
        }


def test_unknown_stack_says_how_to_fix():
    with pytest.raises(ValueError, match="Use one of: python, typescript"):
        load_recipe("cobol")


def test_check_commands_keep_order_and_skip_empty():
    commands = {"test": "t", "setup": "s", "lint": "", "format": "f"}
    assert check_commands(commands) == [("setup", "s"), ("test", "t")]


@pytest.mark.parametrize("stack", ["python", "typescript"])
def test_every_recipe_has_every_check_step_and_pinned_ci_actions(stack: str):
    recipe = load_recipe(stack)
    assert [step for step, _ in check_commands(recipe.commands)] == list(CHECK_STEPS)
    assert recipe.ci.steps, f"{stack}: CI needs a step that installs its toolchain"
    for step in recipe.ci.steps:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@v\d+(\.\d+\.\d+)?", step["uses"])
    assert recipe.ignores
    assert all(isinstance(v, str) for v in recipe.ci.env.values())


def test_recipes_name_no_stack_outside_recipes():
    # Stack facts live in recipes/, so a new stack needs no code change.
    # answers.STACKS is the one exception until the generic-stack plan.
    src = PLUGIN_ROOT / "src" / "alpha"
    found = [
        f"{path.relative_to(src)}:{n}"
        for path in sorted(src.rglob("*.py"))
        if path.name != "answers.py"
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if re.search(r"[\"'](python|typescript)[\"']", line)
    ]
    assert found == []
