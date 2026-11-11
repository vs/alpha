"""Baselines switched on from the answers (spec §8b): which commands run
through the ratchet, and what a project without baselines keeps."""

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from helpers import SCENARIOS, TODAY

from alpha.answers import AnswersError, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.generate import PRINCIPLES_TOML, render_project
from alpha.render.ci import WORKFLOW

SOURCE = Source(PLUGIN_ROOT, True)
D = load_defaults(SOURCE)
SCENARIO_NAMES = sorted(p.stem for p in SCENARIOS.glob("*.json"))


def _scenario(name: str) -> dict[str, Any]:
    return json.loads((SCENARIOS / f"{name}.json").read_text())


def _texts(tmp_path: Path, data: dict[str, Any]) -> dict[str, str]:
    path = tmp_path / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return render_project(tmp_path, load_answers(path), D, 2026, TODAY).texts


def _baselined(tmp_path: Path, name: str, checks: list[str]) -> dict[str, str]:
    data = _scenario(name)
    data["adoption"] = {"baselines": checks}
    return _texts(tmp_path, data)


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_no_baselines_renders_as_before(tmp_path: Path, name: str):
    plain = _texts(tmp_path / "plain", _scenario(name))
    data = _scenario(name)
    data["adoption"] = {"baselines": []}
    assert _texts(tmp_path / "empty", data) == plain
    assert "baselines" not in tomllib.loads(plain[PRINCIPLES_TOML])


def test_baselined_step_is_wrapped(tmp_path: Path):
    texts = _baselined(
        tmp_path, "web-ts-plus-python-api", ["typecheck:api", "lint:web"]
    )
    principles = tomllib.loads(texts[PRINCIPLES_TOML])
    comps = {c["name"]: c for c in principles["components"]}
    ratchet = "python3 ../.claude/alpha/checks/ratchet.py"
    assert comps["api"]["commands"]["typecheck"] == f"{ratchet} typecheck:api"
    assert comps["api"]["commands"]["lint"] == "uv run ruff check"
    assert comps["web"]["commands"]["lint"] == f"{ratchet} lint:web"
    assert (
        comps["web"]["commands"]["lint_file"] == f"{ratchet} lint:web --file {{file}}"
    )
    entries = {e["id"]: e for e in principles["baselines"]}
    assert entries["typecheck:api"] == {
        "id": "typecheck:api",
        "dir": "api",
        "command": "uv run pyright --outputjson",
        "json": {
            "items": "generalDiagnostics.*",
            "file": "file",
            "rule": "rule",
            "where": {"severity": "error"},
        },
    }
    assert entries["lint:web"]["file_command"].endswith("{file}")
    # CI and mise run the same wrapped commands.
    jobs = yaml.safe_load(texts[WORKFLOW])["jobs"]
    runs = [s.get("run") for s in jobs["api"]["steps"]]
    assert f"{ratchet} typecheck:api" in runs
    mise = tomllib.loads(texts["mise.toml"])
    assert f"{ratchet} lint:web" in mise["tasks"]["check:component:web"]["run"]


def test_root_component_wrap(tmp_path: Path):
    name = _scenario("python-ml-single")["components"][0]["name"]
    texts = _baselined(tmp_path, "python-ml-single", [f"test:{name}"])
    comp = tomllib.loads(texts[PRINCIPLES_TOML])["components"][0]
    assert comp["commands"]["test"] == (
        f"python3 .claude/alpha/checks/ratchet.py test:{name}"
    )


def test_baselined_repo_check(tmp_path: Path):
    texts = _baselined(tmp_path, "web-ts-plus-python-api", ["typos"])
    mise = tomllib.loads(texts["mise.toml"])["tasks"]
    assert mise["check:typos"]["run"] == "python3 .claude/alpha/checks/ratchet.py typos"
    assert mise["check:baselines"]["run"].endswith("diff_checks.py baselines")
    assert "check:baselines" in mise["ci"]["depends"]
    principles = tomllib.loads(texts[PRINCIPLES_TOML])
    assert ".claude/alpha/baselines/**" in principles["protected"]["paths"]
    assert ".claude/alpha/baselines/**" in principles["review"]["risk_paths"]
    [entry] = principles["baselines"]
    assert entry["id"] == "typos" and entry["dir"] == "."
    assert entry["command"] == "typos --format brief"


@pytest.mark.parametrize(
    ("check", "message"),
    [
        ("format_check:api", "formatting is fixed once"),
        ("setup:api", "isn't a check of the code"),
        ("secrets", "betterleaksignore"),
        ("baselines", "keeps baselines from growing"),
        ("nope:api", "isn't a step a baseline can hold"),
        ("typecheck:ghost", "no component named 'ghost'"),
        ("structure:web", "the typescript recipe has no [baseline.structure]"),
        ("spelling", "isn't a check a baseline can hold"),
    ],
)
def test_refused_baselines(tmp_path: Path, check: str, message: str):
    data = _scenario("web-ts-plus-python-api")
    data["adoption"] = {"baselines": ["typos", check]}
    with pytest.raises(AnswersError, match=r"adoption\.baselines\[1\]") as e:
        _texts(tmp_path, data)
    assert message in str(e.value)


def test_twice_and_unknown_keys_refused(tmp_path: Path):
    data = _scenario("web-ts-plus-python-api")
    data["adoption"] = {"baselines": ["typos", "typos"]}
    with pytest.raises(AnswersError, match="listed twice"):
        _texts(tmp_path / "a", data)
    data["adoption"] = {"steps": []}
    with pytest.raises(AnswersError, match=r"adoption\.steps: unknown key"):
        _texts(tmp_path / "b", data)


def test_a_check_the_project_lacks_is_refused(tmp_path: Path):
    data = _scenario("rust-cli")
    data["build"]["ci"] = "none"
    data["overrides"].append(
        {
            "principle": "build-hosting-upfront",
            "scope": "project",
            "change": "loosen",
            "params": {},
            "reason": "No CI yet.",
        }
    )
    data["adoption"] = {"baselines": ["actions"]}
    with pytest.raises(AnswersError, match="the project has no actions check"):
        _texts(tmp_path, data)
