import copy
import json
from pathlib import Path
from typing import Any

import pytest
from helpers import single_component

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


def test_fixture_loads_security_dependencies_observability():
    a = load_answers(FIXTURE)
    assert a.security and a.security.extra_protected == ("api/keys/**",)
    assert a.dependencies and a.dependencies.updates == "dependabot"
    assert a.observability
    assert [c.name for c in a.observability.components] == ["api", "web"]


def test_deployed_projects_need_a_secret_store(tmp_path: Path):
    d = valid()
    d["security"]["secret_store"] = " "
    with pytest.raises(AnswersError, match=r"security\.secret_store: "):
        check(tmp_path, d)


def test_auth_is_required(tmp_path: Path):
    d = valid()
    d["security"]["auth"] = ""
    with pytest.raises(AnswersError, match=r"security\.auth"):
        check(tmp_path, d)


@pytest.mark.parametrize("glob", ["/etc/**", "keys/", "./keys/**", ""])
def test_extra_protected_globs_must_match_something(tmp_path: Path, glob: str):
    d = valid()
    d["security"]["extra_protected"] = [glob]
    with pytest.raises(AnswersError, match=r"security\.extra_protected\[0\]"):
        check(tmp_path, d)


@pytest.mark.parametrize(
    ("key", "value"), [("updates", "renovate"), ("schedule", "hourly")]
)
def test_update_tool_and_schedule_choices(tmp_path: Path, key: str, value: str):
    d = valid()
    d["dependencies"][key] = value
    with pytest.raises(AnswersError, match=rf"dependencies\.{key}: "):
        check(tmp_path, d)


def test_observability_covers_exactly_the_deployed_components(tmp_path: Path):
    d = valid()
    d["observability"]["components"].pop(0)
    with pytest.raises(AnswersError, match=r"observability\.components: .*'api'"):
        check(tmp_path, d)
    d = valid()
    d["components"][1]["traits"]["deployed"] = False
    d["build"]["components"][1]["hosting"] = ""
    with pytest.raises(
        AnswersError, match=r"observability\.components\[1\]\.name: .*isn't deployed"
    ):
        check(tmp_path, d)


def test_nothing_deployed_needs_no_observability_or_secret_store(tmp_path: Path):
    d = valid()
    for c in d["components"]:
        c["traits"]["deployed"] = False
    for t in d["build"]["components"]:
        t["hosting"] = ""
    d["build"]["environments"] = []
    d["security"]["secret_store"] = ""
    d["observability"]["components"] = []
    a = check(tmp_path, d)
    assert a.observability and a.observability.components == ()


def test_correlation_none_only_with_one_deployed_component(tmp_path: Path):
    d = valid()
    d["observability"]["components"][0]["correlation"] = "none"
    with pytest.raises(
        AnswersError, match=r"observability\.components\[0\]\.correlation: "
    ):
        check(tmp_path, d)


@pytest.mark.parametrize("field", ["log_format", "correlation", "telemetry"])
def test_observability_choices(tmp_path: Path, field: str):
    d = valid()
    d["observability"]["components"][0][field] = "text"
    with pytest.raises(AnswersError, match=rf"observability\.components\[0\]\.{field}"):
        check(tmp_path, d)


def test_talking_components_need_a_call(tmp_path: Path):
    d = valid()
    d["architecture"]["components"][1]["calls"] = []
    with pytest.raises(
        AnswersError,
        match=r"architecture\.components: .*no component calls another.*"
        r"set components_talk to false",
    ):
        check(tmp_path, d)


def test_contract_error_says_how_to_turn_talking_off(tmp_path: Path):
    d = valid()
    d["architecture"]["contracts"] = {"format": "none", "paths": []}
    with pytest.raises(AnswersError, match=r"contracts\.format: .*components_talk"):
        check(tmp_path, d)


def test_one_component_cannot_talk(tmp_path: Path):
    d = valid()
    single_component(d)
    d["components_talk"] = True
    with pytest.raises(AnswersError, match=r"components_talk: .*only one component"):
        check(tmp_path, d)


def scenario(name: str) -> dict[str, Any]:
    from helpers import SCENARIOS

    return json.loads((SCENARIOS / f"{name}.json").read_text())


def test_fixture_loads_ui_and_accessibility():
    a = load_answers(FIXTURE)
    assert a.ui and [c.name for c in a.ui.components] == ["web"]
    web = a.ui.components[0]
    assert web.tokens == "web/src/styles/tokens.css"
    assert web.theming == "light-dark"
    assert a.accessibility and a.accessibility.level == "WCAG 2.2 AA"
    assert a.accessibility.components[0].checks.startswith("axe")


@pytest.mark.parametrize("area", ["ui", "accessibility"])
def test_ui_areas_refuse_components_without_a_ui(tmp_path: Path, area: str):
    d = valid()
    entry = copy.deepcopy(d[area]["components"][0])
    entry["name"] = "api"
    d[area]["components"].insert(0, entry)
    with pytest.raises(
        AnswersError, match=rf"{area}\.components\[0\]\.name: .*has no UI"
    ):
        check(tmp_path, d)


@pytest.mark.parametrize("name", ["python-ml-single", "rust-cli"])
def test_projects_without_a_ui_have_empty_ui_answers(tmp_path: Path, name: str):
    a = check(tmp_path, scenario(name))
    assert a.ui and a.ui.components == ()
    assert a.accessibility and a.accessibility.level == ""
    assert a.accessibility.components == ()


def test_a_ui_needs_an_accessibility_level(tmp_path: Path):
    d = valid()
    d["accessibility"]["level"] = ""
    with pytest.raises(AnswersError, match=r"accessibility\.level: .*WCAG 2\.2 AA"):
        check(tmp_path, d)


def test_no_ui_means_no_accessibility_level(tmp_path: Path):
    d = scenario("rust-cli")
    d["accessibility"]["level"] = "WCAG 2.2 AA"
    with pytest.raises(AnswersError, match=r"accessibility\.level: .*no component"):
        check(tmp_path, d)


def test_bad_theming_lists_choices(tmp_path: Path):
    d = valid()
    d["ui"]["components"][0]["theming"] = "neon"
    with pytest.raises(
        AnswersError, match=r"ui\.components\[0\]\.theming: .*light-dark"
    ):
        check(tmp_path, d)


@pytest.mark.parametrize("tokens", ["./web/tokens.css", "/tokens.css", ""])
def test_tokens_must_be_a_relative_path(tmp_path: Path, tokens: str):
    d = valid()
    d["ui"]["components"][0]["tokens"] = tokens
    with pytest.raises(AnswersError, match=r"ui\.components\[0\]\.tokens"):
        check(tmp_path, d)


@pytest.mark.parametrize(
    ("area", "field"),
    [
        ("ui", "library"),
        ("ui", "icons"),
        ("ui", "typography"),
        ("ui", "visual_regression"),
        ("accessibility", "checks"),
    ],
)
def test_ui_text_fields_are_required(tmp_path: Path, area: str, field: str):
    d = valid()
    d[area]["components"][0][field] = " "
    with pytest.raises(AnswersError, match=rf"{area}\.components\[0\]\.{field}"):
        check(tmp_path, d)


def test_ui_areas_follow_renames(tmp_path: Path):
    for area in ("ui", "accessibility"):
        d = valid()
        d["components"][1]["name"] = "site"
        d["git"]["scopes"] = ["api", "site"]
        for other in ("architecture", "errors", "testing", "build", "observability"):
            d[other]["components"][1]["name"] = "site"
        d["architecture"]["components"][1]["calls"] = ["api"]
        for other in ("ui", "accessibility"):
            if other != area:
                d[other]["components"][0]["name"] = "site"
        with pytest.raises(AnswersError, match=rf"{area}\.components"):
            check(tmp_path, d)


def test_fixture_loads_releases_data_and_performance():
    a = load_answers(FIXTURE)
    assert a.releases and (a.releases.scheme, a.releases.scope) == ("semver", "repo")
    assert a.data and [c.name for c in a.data.components] == ["api"]
    assert a.data.components[0].migrations == ("api/migrations/versions/**",)
    assert a.data.components[0].reversible is True
    assert a.data.ml is None
    assert a.performance
    assert [c.name for c in a.performance.components] == ["api", "web"]
    assert a.performance.components[0].budgets[0].limit == "300 ms"


def test_release_scope_component_needs_several_components(tmp_path: Path):
    d = valid()
    single_component(d)
    d["releases"]["scope"] = "component"
    with pytest.raises(
        AnswersError, match=r"releases\.scope: .*more than one component"
    ):
        check(tmp_path, d)
    d = valid()
    d["releases"]["scope"] = "component"
    assert check(tmp_path, d).releases


@pytest.mark.parametrize(
    ("key", "value"),
    [("scheme", "romver"), ("changelog", "wiki"), ("scope", "team"), ("process", "")],
)
def test_release_fields(tmp_path: Path, key: str, value: str):
    d = valid()
    d["releases"][key] = value
    with pytest.raises(AnswersError, match=rf"releases\.{key}: "):
        check(tmp_path, d)


def test_data_entries_need_a_component_that_stores_data(tmp_path: Path):
    d = valid()
    entry = {**d["data"]["components"][0], "name": "web"}
    d["data"]["components"].append(entry)
    with pytest.raises(
        AnswersError, match=r"data\.components\[1\]\.name: .*doesn't store data"
    ):
        check(tmp_path, d)


def test_migrations_are_needed_with_a_migration_tool(tmp_path: Path):
    d = valid()
    d["data"]["components"][0]["migrations"] = []
    with pytest.raises(AnswersError, match=r"data\.components\[0\]\.migrations: "):
        check(tmp_path, d)
    d["data"]["components"][0]["migration_tool"] = "none"
    assert check(tmp_path, d).data


@pytest.mark.parametrize("glob", ["./api/migrations/**", "/migrations/**"])
def test_migration_globs_must_match_something(tmp_path: Path, glob: str):
    d = valid()
    d["data"]["components"][0]["migrations"] = [glob]
    with pytest.raises(AnswersError, match=r"data\.components\[0\]\.migrations\[0\]"):
        check(tmp_path, d)


def test_ml_data_follows_the_ml_trait(tmp_path: Path):
    d = scenario("python-ml-single")
    a = check(tmp_path, d)
    assert a.data and a.data.components == () and a.data.ml
    assert a.data.ml.versioning == "DVC"
    d["data"]["ml"] = None
    with pytest.raises(AnswersError, match=r"data\.ml: .*ML"):
        check(tmp_path, d)
    d = valid()
    d["data"]["ml"] = {"versioning": "DVC", "seeds": "fixed", "tracking": "MLflow"}
    with pytest.raises(AnswersError, match=r"data\.ml: .*no component does ML"):
        check(tmp_path, d)


@pytest.mark.parametrize("field", ["versioning", "seeds", "tracking"])
def test_ml_data_fields_are_required(tmp_path: Path, field: str):
    d = scenario("python-ml-single")
    d["data"]["ml"][field] = ""
    with pytest.raises(AnswersError, match=rf"data\.ml\.{field}"):
        check(tmp_path, d)


@pytest.mark.parametrize("field", ["metric", "limit", "measured_by"])
def test_budget_fields_are_required(tmp_path: Path, field: str):
    d = valid()
    d["performance"]["components"][0]["budgets"][0][field] = " "
    with pytest.raises(
        AnswersError,
        match=rf"performance\.components\[0\]\.budgets\[0\]\.{field}",
    ):
        check(tmp_path, d)


def test_empty_budgets_are_fine(tmp_path: Path):
    d = valid()
    d["performance"]["components"][1]["budgets"] = []
    a = check(tmp_path, d)
    assert a.performance and a.performance.components[1].budgets == ()


@pytest.mark.parametrize("area", ["data", "performance"])
def test_data_and_performance_follow_renames(tmp_path: Path, area: str):
    d = valid()
    d["components"][0]["name"] = "server"
    d["git"]["scopes"] = ["server", "web"]
    for other in ("architecture", "errors", "testing", "build", "observability"):
        d[other]["components"][0]["name"] = "server"
    d["architecture"]["components"][1]["calls"] = ["server"]
    d["overrides"][0]["scope"] = "component:server"
    for other in ("data", "performance"):
        if other != area:
            d[other]["components"][0]["name"] = "server"
    with pytest.raises(AnswersError, match=rf"{area}\.components"):
        check(tmp_path, d)


def test_a_frontend_has_a_ui_whatever_its_trait_says(tmp_path: Path):
    d = valid()
    d["components"][1]["traits"]["has_ui"] = False
    a = check(tmp_path, d)
    assert a.ui and [c.name for c in a.ui.components] == ["web"]
    d["ui"]["components"] = []
    with pytest.raises(AnswersError, match=r"ui\.components: no entry .*'web'"):
        check(tmp_path, d)
