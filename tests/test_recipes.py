import json
import tomllib

import pytest

from alpha.answers import Component, Traits
from alpha.recipes import load_recipe, render_component


def _component(stack: str, kind: str, name: str, path: str) -> Component:
    traits = Traits(False, False, False, False, False, False)
    return Component(name=name, path=path, kind=kind, stack=stack, traits=traits)


def py_component(name: str = "api", path: str = "api") -> Component:
    return _component("python", "backend", name, path)


def ts_component(name: str = "web", path: str = "web") -> Component:
    return _component("typescript", "frontend", name, path)


def test_python_component_files():
    files = render_component(py_component(path="api"), "pico")
    assert set(files) == {"api/pyproject.toml", "api/tests/test_setup.py"}
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
    }
    tsc = json.loads(files["web/tsconfig.json"])
    assert tsc["compilerOptions"]["strict"] is True
    pkg = json.loads(files["web/package.json"])
    assert pkg["type"] == "module" and pkg["name"] == "pico-web"
    json.loads(files["web/biome.json"])


def test_single_layout_path_dot():
    files = render_component(py_component(path="."), "pico")
    assert set(files) == {"pyproject.toml", "tests/test_setup.py"}


def test_command_keys_complete():
    for s in ("python", "typescript"):
        assert set(load_recipe(s).commands) == {
            "setup",
            "test",
            "lint",
            "format",
            "typecheck",
            "format_file",
            "lint_file",
        }


def test_unknown_stack_says_how_to_fix():
    with pytest.raises(ValueError, match="Use one of: python, typescript"):
        load_recipe("cobol")
