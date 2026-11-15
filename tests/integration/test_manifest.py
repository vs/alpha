import json
from datetime import date
from pathlib import Path

from helpers import SCENARIOS, TODAY, GenerateScenario

from alpha.answers import PROJECT_JSON, answers_snapshot, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles
from alpha.render.docs import render_docs

SCENARIO = SCENARIOS / "web-ts-plus-python-api.json"


def test_dependency_rows_use_each_components_added_date():
    a = load_answers(SCENARIO)
    d = load_defaults(Source(PLUGIN_ROOT, True))
    out = render_docs(
        a,
        build_principles(d, a, "0.1.0"),
        2026,
        TODAY,
        added={"api": date(2026, 10, 1)},
    )
    rows = [
        line
        for line in out["docs/alpha/dependencies.md"].splitlines()
        if line.startswith("| ") and line.endswith("|")
    ]
    api = [r for r in rows if "| api |" in r]
    web = [r for r in rows if "| web |" in r]
    assert api and web
    assert all(r.endswith("| 2026-10-01 |") for r in api)
    assert all(r.endswith(f"| {TODAY.isoformat()} |") for r in web)


def test_generate_records_the_applied_answers_and_added_dates(
    tmp_path: Path, generate_scenario: GenerateScenario
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    data = json.loads((tmp_path / PROJECT_JSON).read_text())
    m = data["manifest"]
    assert m["applied"] == answers_snapshot(data)
    assert m["added"] == {"api": TODAY.isoformat(), "web": TODAY.isoformat()}
    assert "records" not in m
