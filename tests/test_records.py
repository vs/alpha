import json
from dataclasses import replace
from datetime import date

from helpers import SCENARIOS, TODAY

from alpha.answers import PROJECT_JSON, answers_snapshot, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles
from alpha.records import Records, record_number, record_paths
from alpha.render.docs import render_docs

SCENARIO = SCENARIOS / "web-ts-plus-python-api.json"


def test_fresh_numbering_matches_generation(tmp_path, generate_scenario):
    files = generate_scenario(tmp_path, "web-ts-plus-python-api")
    a = load_answers(tmp_path / PROJECT_JSON)
    r = record_paths(a)
    assert sorted([*r.decisions, *r.overrides]) == [
        f for f in files if f.startswith("docs/decisions/0")
    ]


def test_known_paths_stay_and_new_ones_follow_the_highest_number(tmp_path):
    base = load_answers(SCENARIO)
    a = replace(
        base,
        decisions=(*base.decisions[:3], replace(base.decisions[0], title="Fourth")),
        overrides=(base.overrides[0], replace(base.overrides[0], principle="x")),
    )
    assert len(a.decisions) == 4 and len(a.overrides) == 2
    known = Records(
        (
            "docs/decisions/0001-a.md",
            "docs/decisions/0002-b.md",
            "docs/decisions/0003-c.md",
        ),
        ("docs/decisions/0004-override-x.md",),
    )
    r = record_paths(a, known=known, taken={1, 2, 3, 4, 14})
    assert r.decisions[:3] == known.decisions
    assert r.overrides[0] == known.overrides[0]
    assert record_number(r.decisions[3]) == 15
    assert r.decisions[3].endswith("-fourth.md")
    assert record_number(r.overrides[1]) == 16


def test_records_json_round_trip_and_malformed():
    r = Records(("docs/decisions/0001-a.md",), ())
    assert Records.from_json(r.to_json()) == r
    assert Records.from_json("x") is None
    assert Records.from_json({"decisions": [1], "overrides": []}) is None
    assert Records.from_json({"decisions": []}) is None
    assert (
        Records.from_json({"decisions": ["docs/decisions/x.md"], "overrides": []})
        is None
    )


def test_dependency_rows_use_each_components_added_date():
    a = load_answers(SCENARIO)
    d = load_defaults(Source(PLUGIN_ROOT, True, ""))
    out = render_docs(
        a,
        build_principles(d, a, "0.1.0"),
        2026,
        TODAY,
        added={"api": date(2026, 10, 1)},
    )
    rows = [
        line
        for line in out["docs/dependencies.md"].splitlines()
        if line.startswith("| ") and line.endswith("|")
    ]
    api = [r for r in rows if "| api |" in r]
    web = [r for r in rows if "| web |" in r]
    assert api and web
    assert all(r.endswith("| 2026-10-01 |") for r in api)
    assert all(r.endswith(f"| {TODAY.isoformat()} |") for r in web)


def test_generate_records_applied_answers_records_and_added(
    tmp_path, generate_scenario
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    data = json.loads((tmp_path / PROJECT_JSON).read_text())
    m = data["manifest"]
    assert m["applied"] == answers_snapshot(data)
    assert Records.from_json(m["records"]) == record_paths(
        load_answers(tmp_path / PROJECT_JSON)
    )
    assert m["added"] == {"api": TODAY.isoformat(), "web": TODAY.isoformat()}
