from pathlib import Path

import pytest

from alpha_evals.scenario import (
    SCENARIOS,
    Mismatch,
    ScenarioError,
    compare,
    load_brief,
    resolve,
)


@pytest.mark.parametrize("name", SCENARIOS)
def test_every_expected_pointer_resolves_in_the_scenario(name: str):
    brief = load_brief(name)
    assert brief.expect
    for pointer in brief.expect:
        resolve(brief.answers, pointer)  # raises KeyError if the brief drifted


@pytest.mark.parametrize("name", SCENARIOS)
def test_brief_ends_with_the_two_standing_rules(name: str):
    text = load_brief(name).text
    assert "For anything these notes don't settle, take the recommendation." in text
    assert "say no." in text.strip().splitlines()[-1]


def test_selector_segment_picks_by_key():
    data = {"components": [{"name": "a", "x": 1}, {"name": "b", "x": 2}]}
    assert resolve(data, "/components[name=b]/x") == 2
    assert resolve(data, "/components/0/x") == 1
    with pytest.raises(KeyError):
        resolve(data, "/components[name=c]/x")


def test_compare_ignores_order_of_string_lists_and_reports_the_rest():
    expected = {"git": {"scopes": ["api", "web"]}, "layout": "monorepo", "x": 1}
    actual = {"git": {"scopes": ["web", "api"]}, "layout": "single"}
    got = compare(expected, actual, ["/git/scopes", "/layout", "/x"])
    assert got == [
        Mismatch("/layout", "monorepo", "single", False),
        Mismatch("/x", 1, None, True),
    ]


def test_unknown_scenario_names_the_missing_file(tmp_path: Path):
    with pytest.raises(ScenarioError, match=r"evals/briefs/nope\.toml"):
        load_brief("nope", root=tmp_path)


def test_a_brief_without_expect_is_refused(tmp_path: Path):
    (tmp_path / "evals/briefs").mkdir(parents=True)
    (tmp_path / "evals/briefs/x.toml").write_text('brief = "hi"\n')
    with pytest.raises(ScenarioError, match="expect"):
        load_brief("x", root=tmp_path)


def test_a_tilde_pointer_accepts_text_that_contains_the_value():
    expected = {"data": {"tracking": "MLflow"}}
    ok = {"data": {"tracking": "MLflow with a local file store"}}
    other = {"data": {"tracking": "Weights & Biases"}}
    assert compare(expected, ok, ["~/data/tracking"]) == []
    assert compare(expected, other, ["~/data/tracking"]) == [
        Mismatch("~/data/tracking", "MLflow", "Weights & Biases", False)
    ]
    assert compare(expected, ok, ["/data/tracking"]) != []  # exact without ~
