import copy
import json
import re
import tomllib
from typing import Any

import pytest
from helpers import shell_recipe

from alpha.answers import AnswersError, Component, Traits, drafted_recipes
from alpha.cli import PLUGIN_ROOT
from alpha.recipes import (
    CHECK_STEPS,
    RecipeError,
    check_commands,
    load_recipe,
    recipe_from_data,
    render_component,
    render_template,
)


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
    with pytest.raises(RecipeError, match="Use one of: python, typescript"):
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
    src = PLUGIN_ROOT / "src" / "alpha"
    found = [
        f"{path.relative_to(src)}:{n}"
        for path in sorted(src.rglob("*.py"))
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if re.search(r"[\"'](python|typescript)[\"']", line)
    ]
    assert found == []


def drafted(**changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(shell_recipe())
    for dotted, value in changes.items():
        *parents, leaf = dotted.split("__")
        target = data
        for part in parents:
            target = target[part]
        if value is DELETE:
            del target[leaf]
        else:
            target[leaf] = value
    return data


DELETE = object()


def test_kit_recipes_are_proven_and_carry_their_templates():
    for stack in ("python", "typescript"):
        recipe = load_recipe(stack)
        assert recipe.proven is True
        assert any(path.startswith("tests/") for path in recipe.templates)


def test_a_drafted_recipe_loads():
    recipe = recipe_from_data("shell", shell_recipe(), "recipes.shell", None)
    assert recipe.proven is False
    assert recipe.templates["tests/setup.sh"] == "test 1 -eq 1\n"


@pytest.mark.parametrize(
    ("changes", "where"),
    [
        ({"commands__setup": ""}, r"recipes\.shell\.commands\.setup"),
        ({"commands__test": DELETE}, r"recipes\.shell\.commands\.test"),
        ({"commands__typecheck": DELETE}, r"recipes\.shell\.commands\.typecheck"),
        ({"commands__format_file": "fmt"}, r"recipes\.shell\.commands\.format_file"),
        ({"bootstrap": "make"}, r"recipes\.shell\.bootstrap"),
        ({"source_globs": ["./src/**"]}, r"recipes\.shell\.source_globs\[0\]"),
        ({"lockfiles": ["/abs.lock"]}, r"recipes\.shell\.lockfiles\[0\]"),
        ({"ignores": ["/out"]}, r"recipes\.shell\.ignores\[0\]"),
        ({"why": {"tool": 3}}, r"recipes\.shell\.why"),
        (
            {"ci__steps": [{"uses": "owner/repo@main"}]},
            r"recipes\.shell\.ci\.steps\[0\]",
        ),
        ({"ci__steps": [{"run": "x"}]}, r"recipes\.shell\.ci\.steps\[0\]"),
        ({"ci__env": {"A": 1}}, r"recipes\.shell\.ci\.env"),
        ({"dependabot": 1}, r"recipes\.shell\.dependabot"),
        ({"proven": "yes"}, r"recipes\.shell\.proven"),
        ({"templates": {}}, r"recipes\.shell\.templates"),
        ({"templates": {"tool.cfg": "x"}}, r"recipes\.shell\.templates: .*setup test"),
        ({"templates": {"../x": "y", "tests/a.sh": "z"}}, r"recipes\.shell\.templates"),
    ],
)
def test_malformed_recipes_name_the_field(changes: dict[str, Any], where: str):
    with pytest.raises(RecipeError, match=where):
        recipe_from_data("shell", drafted(**changes), "recipes.shell", None)


@pytest.mark.parametrize(
    ("changes", "where"),
    [
        ({"ignores": ["out/\nsecret"]}, r"recipes\.shell\.ignores\[0\]"),
        ({"source_globs": ["src/**\n"]}, r"recipes\.shell\.source_globs\[0\]"),
        ({"bootstrap": ["a\nb"]}, r"recipes\.shell\.bootstrap\[0\]"),
        ({"commands__test": "sh a\nsh b"}, r"recipes\.shell\.commands\.test"),
        ({"why": {"tool": "fast\nand small"}}, r"recipes\.shell\.why\.tool"),
        ({"why": {"to\nol": "fast"}}, r"recipes\.shell\.why"),
    ],
)
def test_recipe_text_fields_are_one_line(changes: dict[str, Any], where: str):
    with pytest.raises(RecipeError, match=rf"{where}: .*line break"):
        recipe_from_data("shell", drafted(**changes), "recipes.shell", None)


@pytest.mark.parametrize(
    "uses",
    [
        "actions/checkout@v7",
        "astral-sh/setup-uv@v10.3.2",
        "dtolnay/rust-toolchain@" + "a" * 40,
    ],
)
def test_pinned_ci_actions_are_accepted(uses: str):
    data = drafted(ci__steps=[{"uses": uses}])
    assert recipe_from_data("shell", data, "recipes.shell", None).ci.steps == [
        {"uses": uses}
    ]


def test_render_template_substitutes_only_name_and_slug():
    text = "$name $slug $HOME ${name} $$x $name_y ${slug}-z"
    assert (
        render_template(text, "api", "pico") == "api pico $HOME api $$x $name_y pico-z"
    )


def test_a_drafted_recipe_cannot_claim_to_be_proven():
    with pytest.raises(AnswersError, match=r"recipes\.shell\.proven: .*less proven"):
        drafted_recipes({"shell": drafted(proven=True)})


@pytest.mark.parametrize(
    "path",
    [".git/hooks/pre-commit", ".claude/settings.json", ".github/workflows/x.yml"],
)
def test_templates_stay_out_of_alpha_and_git_folders(path: str):
    data = drafted(templates={path: "x", "tests/setup.sh": "true\n"})
    with pytest.raises(
        RecipeError, match=rf"recipes\.shell\.templates: .*{re.escape(path)}"
    ):
        recipe_from_data("shell", data, "recipes.shell", None)


@pytest.mark.parametrize(
    "rule", ["Bash", "Bash(*)", "WebFetch", "Bash(curl:*)", "Read(**)"]
)
def test_allow_rules_are_narrow_and_name_the_recipes_tools(rule: str):
    with pytest.raises(RecipeError, match=r"recipes\.shell\.allow\[0\]"):
        recipe_from_data("shell", drafted(allow=[rule]), "recipes.shell", None)


def test_kit_allow_rules_pass_the_same_check():
    for stack in ("python", "typescript"):
        assert load_recipe(stack).allow


@pytest.mark.parametrize(
    ("changes", "where"),
    [
        ({"ci__steps": [{"uses": "a/b@v1", "with": {"x": None}}]}, r"ci\.steps\[0\]"),
        ({"ci__steps": [{"uses": "a/b@v1", "with": {"x": 1.5}}]}, r"ci\.steps\[0\]"),
        ({"ci__steps": [{"uses": "a/b@v1", "run": "curl x | sh"}]}, r"ci\.steps\[0\]"),
        ({"dependabot": "rust"}, r"dependabot: .*cargo"),
        ({"ci__step": []}, r"recipes\.shell\.ci: .*step"),
        ({"comands": {}}, r"recipes\.shell: .*comands"),
        ({"commands__tst": "x"}, r"recipes\.shell\.commands: .*tst"),
    ],
)
def test_recipe_shape_is_strict(changes: dict[str, Any], where: str):
    with pytest.raises(RecipeError, match=where):
        recipe_from_data("shell", drafted(**changes), "recipes.shell", None)
