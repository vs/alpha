import copy
import json
from pathlib import Path
from typing import Any

import pytest

from alpha.answers import AnswersError, load_answers

FIXTURE = Path(__file__).parent / "fixtures" / "answers_valid.json"


def valid() -> dict[str, Any]:
    return copy.deepcopy(json.loads(FIXTURE.read_text()))


def check(tmp_path: Path, data: dict[str, Any]):
    path = tmp_path / "project.json"
    path.write_text(json.dumps(data))
    return load_answers(path)


def test_fixture_loads_the_three_areas():
    a = load_answers(FIXTURE)
    assert a.architecture and a.architecture.components[1].calls == ("api",)
    assert a.architecture.contracts.paths == ("api/openapi.yaml",)
    assert a.architecture.glossary[0].term == "Payload"
    assert a.errors and a.errors.components[0].format == "problem-json"
    assert a.testing and a.testing.components[1].levels == ("unit", "end-to-end")


def test_calls_need_components_that_talk(tmp_path: Path):
    d = valid()
    d["components_talk"] = False
    d["architecture"]["contracts"] = {"format": "none", "paths": []}
    d["testing"]["components"][0]["levels"] = ["unit"]
    with pytest.raises(
        AnswersError, match=r"architecture\.components\[1\]\.calls: .*components_talk"
    ):
        check(tmp_path, d)


@pytest.mark.parametrize("call", ["web", "ghost"])
def test_calls_name_other_components(tmp_path: Path, call: str):
    d = valid()
    d["architecture"]["components"][1]["calls"] = [call]
    with pytest.raises(AnswersError, match=r"architecture\.components\[1\]\.calls"):
        check(tmp_path, d)


def test_talking_components_need_a_contract(tmp_path: Path):
    d = valid()
    d["architecture"]["contracts"] = {"format": "none", "paths": []}
    with pytest.raises(AnswersError, match=r"architecture\.contracts\.format: "):
        check(tmp_path, d)


def test_contract_paths_must_match_something(tmp_path: Path):
    d = valid()
    d["architecture"]["contracts"]["paths"] = ["./api/openapi.yaml"]
    with pytest.raises(AnswersError, match=r"architecture\.contracts\.paths\[0\]"):
        check(tmp_path, d)


def test_no_contract_when_components_do_not_talk(tmp_path: Path):
    d = valid()
    d["components_talk"] = False
    d["architecture"]["components"][1]["calls"] = []
    d["testing"]["components"][0]["levels"] = ["unit"]
    with pytest.raises(AnswersError, match=r"architecture\.contracts\.format: "):
        check(tmp_path, d)
    d["architecture"]["contracts"] = {"format": "none", "paths": []}
    assert check(tmp_path, d).architecture


def test_jargon_needs_a_glossary(tmp_path: Path):
    d = valid()
    d["identity"]["domain_jargon"] = True
    d["architecture"]["glossary"] = []
    with pytest.raises(AnswersError, match=r"architecture\.glossary: "):
        check(tmp_path, d)


def test_duplicate_glossary_terms(tmp_path: Path):
    d = valid()
    d["architecture"]["glossary"][1]["term"] = "payload"
    with pytest.raises(AnswersError, match=r"architecture\.glossary\[1\]\.term: "):
        check(tmp_path, d)


@pytest.mark.parametrize("value", [[], ["Not Found"], ["internal", "internal"]])
def test_error_categories_rules(tmp_path: Path, value: list[str]):
    d = valid()
    d["errors"]["categories"] = value
    with pytest.raises(AnswersError, match=r"errors\.categories"):
        check(tmp_path, d)


def test_bad_error_format_lists_choices(tmp_path: Path):
    d = valid()
    d["errors"]["components"][0]["format"] = "xml"
    with pytest.raises(AnswersError, match=r"errors\.components\[0\]\.format: .*"):
        check(tmp_path, d)


@pytest.mark.parametrize(
    ("levels", "where"),
    [
        (["integration"], "levels"),
        ([], "levels"),
        (["unit", "unit"], "levels"),
        (["unit", "smoke"], r"levels\[1\]"),
    ],
)
def test_levels_rules(tmp_path: Path, levels: list[str], where: str):
    d = valid()
    d["testing"]["components"][0]["levels"] = levels
    with pytest.raises(AnswersError, match=rf"testing\.components\[0\]\.{where}"):
        check(tmp_path, d)


def test_contract_tests_need_components_that_talk(tmp_path: Path):
    d = valid()
    d["components_talk"] = False
    d["architecture"]["components"][1]["calls"] = []
    d["architecture"]["contracts"] = {"format": "none", "paths": []}
    with pytest.raises(
        AnswersError, match=r"testing\.components\[0\]\.levels: .*contract"
    ):
        check(tmp_path, d)


@pytest.mark.parametrize("area", ["architecture", "errors", "testing"])
def test_per_component_areas_follow_renames(tmp_path: Path, area: str):
    d = valid()
    d["components"][1]["name"] = "site"
    d["git"]["scopes"] = ["api", "site"]
    d["build"]["components"][1]["name"] = "site"
    for other in ("architecture", "errors", "testing"):
        if other != area:
            d[other]["components"][1]["name"] = "site"
    d["architecture"]["components"][1]["calls"] = ["api"]
    with pytest.raises(AnswersError, match=rf"{area}\.components"):
        check(tmp_path, d)
