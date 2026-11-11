import copy
import json
import re
import shutil
import tomllib
from pathlib import Path
from typing import Any

import pytest
from helpers import proven, shell_recipe

from alpha.answers import AnswersError, Component, Traits, drafted_recipes
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.recipes import (
    CHECK_STEPS,
    RecipeBook,
    RecipeError,
    check_commands,
    load_recipe,
    recipe_from_data,
    recipe_hash,
    render_component,
    render_template,
)
from alpha.registry import BUNDLED, load_registry


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
        "web/knip.jsonc",
        "web/pnpm-workspace.yaml",
        "web/.dependency-cruiser.cjs",
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
            "structure",
            "format_file",
            "lint_file",
        }


def test_unknown_stack_says_how_to_fix():
    with pytest.raises(RecipeError, match="Use one of: python, typescript"):
        load_recipe("cobol")


def test_check_commands_keep_order_and_skip_empty():
    commands = {"test": "t", "setup": "s", "lint": "", "format": "f"}
    assert check_commands(commands) == [("setup", "s"), ("test", "t")]


def test_structure_step_order():
    steps = [s for s, _ in check_commands(load_recipe("typescript").commands)]
    assert steps.index("typecheck") + 1 == steps.index("structure")
    assert steps.index("structure") + 1 == steps.index("test")


def test_structure_commands():
    assert load_recipe("python").commands["structure"] == "uv run deptry ."
    assert load_recipe("typescript").commands["structure"] == (
        "pnpm knip && pnpm depcruise --config .dependency-cruiser.cjs ."
    )


def test_drafted_recipe_without_structure_valid():
    data = drafted()
    assert "structure" not in data["commands"]
    recipe = recipe_from_data("shell", data, "recipes.shell", None)
    assert recipe.commands["structure"] == ""
    assert "structure" not in dict(check_commands(recipe.commands))


@pytest.mark.parametrize("stack", ["python", "typescript"])
def test_every_recipe_has_every_check_step_and_pinned_ci_actions(stack: str):
    recipe = load_recipe(stack)
    assert [step for step, _ in check_commands(recipe.commands)] == list(CHECK_STEPS)
    assert recipe.ci.steps, f"{stack}: CI needs a step that installs its toolchain"
    for step in recipe.ci.steps:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"])
    assert recipe.ignores
    assert all(isinstance(v, str) for v in recipe.ci.env.values())


def test_recipes_name_no_stack_outside_recipes():
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
    assert recipe.rules == []


def test_a_drafted_recipe_carries_its_rules():
    rules = [{"id": "quote-variables", "rule": "Quote every `$var`."}]
    recipe = recipe_from_data("shell", drafted(rules=rules), "recipes.shell", None)
    assert [(r.id, r.rule) for r in recipe.rules] == [
        ("quote-variables", "Quote every `$var`.")
    ]


def test_kit_recipes_carry_stack_rules():
    assert [r.id for r in load_recipe("python").rules] == [
        "uv-for-dependencies",
        "typed-boundaries",
        "import-contracts",
    ]
    assert [r.id for r in load_recipe("typescript").rules] == [
        "top-level-imports",
        "unknown-at-boundaries",
        "pnpm-for-dependencies",
    ]


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
        ({"rules": {"id": "a"}}, r"recipes\.shell\.rules: must be a list"),
        ({"rules": ["no x"]}, r"recipes\.shell\.rules\[0\]: must be an object"),
        ({"rules": [{"id": "No X", "rule": "x"}]}, r"recipes\.shell\.rules\[0\]\.id"),
        ({"rules": [{"id": "a", "rule": " "}]}, r"recipes\.shell\.rules\[0\]\.rule"),
        ({"rules": [{"id": "a", "rule": "x\ny"}]}, r"rules\[0\]\.rule: .*line break"),
        ({"rules": [{"id": "a", "rule": "x", "why": "y"}]}, r"rules\[0\]: .*why"),
        (
            {"rules": [{"id": "a", "rule": "x"}, {"id": "a", "rule": "y"}]},
            r"recipes\.shell\.rules\[1\]\.id: 'a' is used twice",
        ),
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
        "actions/checkout@" + "b" * 40,
        "dtolnay/rust-toolchain@" + "a" * 40,
    ],
)
def test_pinned_ci_actions_are_accepted(uses: str):
    step = {"uses": uses, "version": "v1.2.3"}
    data = drafted(ci__steps=[step])
    assert recipe_from_data("shell", data, "recipes.shell", None).ci.steps == [step]


def test_kit_recipes_pin_shas():
    book = RecipeBook()
    registry = load_registry(Source(BUNDLED, False))
    for stack in book.kit_stacks():
        for step in book.get(stack).ci.steps:
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"])
            assert step.get("version"), f"{stack}: {step['uses']} has no version"
            repo, sha = step["uses"].split("@")
            action = registry.action(repo)
            assert (sha, step["version"]) == (action.sha, action.version)


def test_drafted_recipe_tag_refused():
    data = drafted(ci__steps=[{"uses": "x/y@v4"}])
    with pytest.raises(RecipeError, match="full commit SHA") as e:
        recipe_from_data("shell", data, "recipes.shell", None)
    assert "git ls-remote" in str(e.value)
    raw = {"shell": data}
    with pytest.raises(AnswersError, match="full commit SHA"):
        drafted_recipes(raw)
    # a project generated earlier keeps working
    assert drafted_recipes(raw, generated=True)["shell"].ci.steps == [
        {"uses": "x/y@v4"}
    ]


def test_drafted_recipe_sha_needs_a_version():
    data = drafted(ci__steps=[{"uses": "x/y@" + "c" * 40}])
    with pytest.raises(RecipeError, match="version"):
        recipe_from_data("shell", data, "recipes.shell", None)


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


def test_older_checkouts_tagged_kit_recipe_says_to_update_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # A live checkout from before SHA pins: its python recipe wins over the
    # plugin's, so the fix is updating the checkout, not pinning by hand.
    checkout = tmp_path / "alpha"
    kit = checkout / "recipes"
    kit.mkdir(parents=True)
    shutil.copytree(PLUGIN_ROOT / "recipes" / "python", kit / "python")
    text = (PLUGIN_ROOT / "recipes" / "python.toml").read_text()
    (kit / "python.toml").write_text(
        re.sub(r"setup-uv@[0-9a-f]{40}", "setup-uv@v10", text)
    )
    monkeypatch.setattr(
        "alpha.recipes.kit_dirs", lambda: [kit, PLUGIN_ROOT / "recipes"]
    )
    with pytest.raises(RecipeError) as e:
        RecipeBook().get("python")
    message = str(e.value)
    assert "isn't pinned to a full commit SHA" in message
    assert f"The alpha checkout at {checkout} is older than the plugin" in message
    assert f"git -C {checkout} pull" in message
    assert "unset ALPHA_SOURCE" in message
    assert "Pin it" not in message


def test_saved_recipe_with_a_tag_still_says_to_pin_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # A recipe saved from an earlier project: the plugin has no copy of it.
    kit = tmp_path / "alpha" / "recipes"
    kit.mkdir(parents=True)
    shutil.copytree(PLUGIN_ROOT / "recipes" / "python", kit / "shellish")
    text = (PLUGIN_ROOT / "recipes" / "python.toml").read_text()
    (kit / "shellish.toml").write_text(
        re.sub(r"setup-uv@[0-9a-f]{40}", "setup-uv@v10", text)
    )
    monkeypatch.setattr(
        "alpha.recipes.kit_dirs", lambda: [kit, PLUGIN_ROOT / "recipes"]
    )
    with pytest.raises(RecipeError, match="Pin it to the commit SHA"):
        RecipeBook().get("shellish")


def test_kit_recipe_with_a_tag_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    kit = tmp_path / "recipes"
    kit.mkdir()
    shutil.copytree(PLUGIN_ROOT / "recipes" / "python", kit / "python")
    text = (PLUGIN_ROOT / "recipes" / "python.toml").read_text()
    text = re.sub(r"setup-uv@[0-9a-f]{40}", "setup-uv@v10", text)
    (kit / "python.toml").write_text(text)
    monkeypatch.setattr("alpha.recipes.kit_dirs", lambda: [kit])
    with pytest.raises(RecipeError, match=r"ci\.steps\[0\].*full commit SHA"):
        RecipeBook().get("python")


def _with_baseline(baseline: dict[str, Any], **commands: str) -> dict[str, Any]:
    raw = shell_recipe()
    raw["commands"].update(commands)
    raw["baseline"] = baseline
    return raw


LINE = r"^(?P<file>[^:]+):\d+: (?P<rule>\w+)"


def test_baseline_pattern_needs_file_and_rule_groups():
    raw = _with_baseline(
        {"lint": {"command": "lint -q", "pattern": r"^(?P<file>\S+)"}}, lint="lint"
    )
    with pytest.raises(RecipeError, match=r"baseline\.lint\.pattern.*\(\?P<rule>"):
        recipe_from_data("sh", raw, "recipe", None)
    raw["baseline"]["lint"]["pattern"] = "("
    with pytest.raises(RecipeError, match="isn't a valid regular expression"):
        recipe_from_data("sh", raw, "recipe", None)


def test_baseline_needs_one_reader():
    both = {"command": "x", "pattern": LINE, "json": {"items": "*", "file": "f"}}
    for entry in ({"command": "x"}, both):
        raw = _with_baseline({"lint": entry}, lint="lint")
        with pytest.raises(RecipeError, match="exactly one of `pattern` and `json`"):
            recipe_from_data("sh", raw, "recipe", None)


def test_baseline_step_must_exist():
    entry = {"command": "tc --json", "pattern": LINE}
    with pytest.raises(RecipeError, match=r"commands\.typecheck is empty"):
        recipe_from_data("sh", _with_baseline({"typecheck": entry}), "recipe", None)
    raw = _with_baseline({"format_check": entry}, format_check="fmt --check")
    with pytest.raises(RecipeError, match="formatting is fixed once"):
        recipe_from_data("sh", raw, "recipe", None)
    with pytest.raises(RecipeError, match="Use one of: lint, typecheck"):
        recipe_from_data("sh", _with_baseline({"deploy": entry}), "recipe", None)


def test_lint_file_command_needs_file_slot():
    entry = {"command": "lint -q", "pattern": LINE}
    raw = _with_baseline({"lint": entry}, lint="lint", lint_file="lint {file}")
    with pytest.raises(RecipeError, match=r"baseline\.lint\.file_command.*missing"):
        recipe_from_data("sh", raw, "recipe", None)
    entry["file_command"] = "lint -q"
    with pytest.raises(RecipeError, match="doesn't say where the file goes"):
        recipe_from_data("sh", raw, "recipe", None)
    entry["file_command"] = "lint -q {file}"
    recipe = recipe_from_data("sh", raw, "recipe", None)
    assert recipe.baselines["lint"].file_command == "lint -q {file}"


def test_json_reader_names_a_walked_key():
    entry = {"command": "x", "json": {"items": "map.*", "file": "@1"}}
    with pytest.raises(RecipeError, match="doesn't name one of the 1 `\\*` steps"):
        recipe_from_data("sh", _with_baseline({"lint": entry}, lint="l"), "r", None)


def test_kit_recipes_have_baselines():
    book = RecipeBook()
    assert set(book.get("python").baselines) == {
        "lint",
        "typecheck",
        "structure",
        "test",
    }
    assert set(book.get("typescript").baselines) == {"lint", "typecheck", "test"}
    for stack in ("python", "typescript"):
        assert "{file}" in book.get(stack).baselines["lint"].file_command


def test_drafted_recipe_carries_its_baseline():
    raw = _with_baseline({"lint": {"command": "lint -q", "pattern": LINE}}, lint="l")
    recipe = drafted_recipes({"sh": proven(raw)})["sh"]
    assert recipe.baselines["lint"].pattern == LINE
    changed = copy.deepcopy(raw)
    changed["baseline"]["lint"]["pattern"] = LINE + "x"
    assert recipe_hash(changed) != recipe_hash(raw)
