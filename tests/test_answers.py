import copy
import json
from pathlib import Path
from typing import Any

import pytest

from alpha import cli
from alpha.answers import AREAS, AnswersError, load_answers

FIXTURE = Path(__file__).parent / "fixtures" / "answers_valid.json"


def write(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "project.json"
    path.write_text(json.dumps(data))
    return path


def valid() -> dict[str, Any]:
    return copy.deepcopy(json.loads(FIXTURE.read_text()))


def check(tmp_path: Path, data: dict[str, Any], **kw: Any):
    return load_answers(write(tmp_path, data), **kw)


def test_valid_fixture_loads():
    a = load_answers(FIXTURE)
    assert a.identity and a.identity.slug == "pico-trust"
    assert [c.name for c in a.components] == ["api", "web"]
    assert a.components[0].traits.deployed is True
    assert a.git and a.git.scopes == ("api", "web")
    assert a.agent_workflow and a.agent_workflow.max_lines == 200
    assert a.overrides[0].scope == "component:api"
    assert {d.area for d in a.decisions} == set(AREAS)


def test_manifest_key_is_ignored(tmp_path: Path):
    d = valid()
    d["manifest"] = {"files": {}}
    assert check(tmp_path, d).identity


def test_unknown_top_level_key(tmp_path: Path):
    d = valid()
    d["colour"] = 1
    with pytest.raises(AnswersError, match=r"colour: unknown key.*Remove"):
        check(tmp_path, d)


def test_missing_file_and_bad_json(tmp_path: Path):
    with pytest.raises(AnswersError, match=r"not found.*alpha interview|Run"):
        load_answers(tmp_path / "nope.json")
    p = tmp_path / "bad.json"
    p.write_text("{")
    with pytest.raises(AnswersError, match=r"not valid JSON.*Fix"):
        load_answers(p)


def test_pending_area_fails_by_default(tmp_path: Path):
    d = valid()
    d["areas"]["git"] = "pending"
    with pytest.raises(AnswersError, match=r"areas\.git: .*pending.*Finish"):
        check(tmp_path, d)


def test_partial_check_only_requires_named_area(tmp_path: Path):
    d = valid()
    d["areas"]["git"] = "pending"
    del d["git"]
    assert check(tmp_path, d, require_areas=["identity"]).git is None


def test_unknown_area_name(tmp_path: Path):
    with pytest.raises(AnswersError, match=r"area: .*nope.*identity"):
        check(tmp_path, valid(), require_areas=["nope"])


@pytest.mark.parametrize("slug", ["Pico", "1abc", "a_b"])
def test_bad_slug(tmp_path: Path, slug: str):
    d = valid()
    d["identity"]["slug"] = slug
    with pytest.raises(AnswersError, match=r"identity\.slug: .*lowercase"):
        check(tmp_path, d)


def test_bad_component_name_and_duplicates(tmp_path: Path):
    d = valid()
    d["components"][1]["name"] = "Web"
    with pytest.raises(AnswersError, match=r"components\[1\]\.name: .*lowercase"):
        check(tmp_path, d)
    d = valid()
    d["components"][1]["name"] = "api"
    with pytest.raises(AnswersError, match=r"components\[1\]\.name: .*duplicate"):
        check(tmp_path, d)


@pytest.mark.parametrize("path", ["/abs", "../up", "a/../b"])
def test_bad_component_path(tmp_path: Path, path: str):
    d = valid()
    d["components"][1]["path"] = path
    with pytest.raises(AnswersError, match=r"components\[1\]\.path: .*relative"):
        check(tmp_path, d)


def test_nested_paths(tmp_path: Path):
    d = valid()
    d["components"][1]["path"] = "api/web"
    with pytest.raises(AnswersError, match=r"components\[1\]\.path: .*inside.*api"):
        check(tmp_path, d)


def test_single_layout_rules(tmp_path: Path):
    d = valid()
    d["layout"] = "single"
    with pytest.raises(AnswersError, match=r"layout: .*single.*exactly one"):
        check(tmp_path, d)
    d["components"] = [d["components"][0]]
    with pytest.raises(AnswersError, match=r"components\[0\]\.path: .*single.*\"\.\""):
        check(tmp_path, d)
    d["components"][0]["path"] = "."
    assert check(tmp_path, d).layout == "single"


def test_unsupported_stack_mentions_supported_ones(tmp_path: Path):
    d = valid()
    d["components"][0]["stack"] = "go"
    with pytest.raises(
        AnswersError,
        match=r"components\[0\]\.stack: go is not supported yet.*python and typescript",
    ):
        check(tmp_path, d)


def test_bad_kind(tmp_path: Path):
    d = valid()
    d["components"][0]["kind"] = "blob"
    with pytest.raises(AnswersError, match=r"components\[0\]\.kind: .*backend"):
        check(tmp_path, d)


def test_trait_must_be_bool(tmp_path: Path):
    d = valid()
    d["components"][0]["traits"]["ml"] = "no"
    with pytest.raises(
        AnswersError, match=r"components\[0\]\.traits\.ml: .*true or false"
    ):
        check(tmp_path, d)


def test_license_rules(tmp_path: Path):
    d = valid()
    d["identity"]["license"] = "GPL"
    with pytest.raises(AnswersError, match=r"identity\.license: .*MIT.*license_file"):
        check(tmp_path, d)
    d["identity"]["license_file"] = str(tmp_path / "LICENSE.txt")
    with pytest.raises(AnswersError, match=r"identity\.license_file: .*does not exist"):
        check(tmp_path, d)
    (tmp_path / "LICENSE.txt").write_text("custom")
    assert check(tmp_path, d).identity


def test_loosen_without_reason(tmp_path: Path):
    d = valid()
    d["overrides"][0]["reason"] = " "
    with pytest.raises(
        AnswersError, match=r"overrides\[0\]\.reason: .*required.*loosen"
    ):
        check(tmp_path, d)


def test_tighten_needs_no_reason(tmp_path: Path):
    d = valid()
    d["overrides"][0].update(change="tighten", reason="")
    assert check(tmp_path, d).overrides[0].change == "tighten"


def test_bad_change_and_scope(tmp_path: Path):
    d = valid()
    d["overrides"][0]["change"] = "relax"
    with pytest.raises(AnswersError, match=r"overrides\[0\]\.change: .*tighten"):
        check(tmp_path, d)
    d = valid()
    d["overrides"][0]["scope"] = "component:ghost"
    with pytest.raises(AnswersError, match=r"overrides\[0\]\.scope: .*ghost.*api"):
        check(tmp_path, d)
    d["overrides"][0]["scope"] = "everywhere"
    with pytest.raises(AnswersError, match=r"overrides\[0\]\.scope: .*project"):
        check(tmp_path, d)


def test_agent_workflow_rules(tmp_path: Path):
    d = valid()
    d["agent_workflow"]["review_mode"] = "never"
    with pytest.raises(AnswersError, match=r"agent_workflow\.review_mode: .*batched"):
        check(tmp_path, d)
    d = valid()
    d["agent_workflow"]["max_lines"] = 0
    with pytest.raises(
        AnswersError, match=r"agent_workflow\.max_lines: .*greater than 0"
    ):
        check(tmp_path, d)
    d = valid()
    d["agent_workflow"]["max_files"] = True
    with pytest.raises(
        AnswersError, match=r"agent_workflow\.max_files: .*whole number"
    ):
        check(tmp_path, d)


def test_decision_required_for_each_done_area(tmp_path: Path):
    d = valid()
    d["decisions"] = [x for x in d["decisions"] if x["area"] != "git"]
    with pytest.raises(AnswersError, match=r"decisions: .*git.*Add"):
        check(tmp_path, d)


def test_missing_field_names_path(tmp_path: Path):
    d = valid()
    del d["identity"]["requirements"][1]["acceptance"]
    with pytest.raises(
        AnswersError, match=r"identity\.requirements\[1\]\.acceptance: .*missing"
    ):
        check(tmp_path, d)


def test_cli_answers_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    assert cli.main(["answers", "check", str(FIXTURE)]) == 0
    assert capsys.readouterr().out.strip() == "ok"
    d = valid()
    d["areas"]["git"] = "pending"
    p = write(tmp_path, d)
    assert cli.main(["answers", "check", str(p)]) == 1
    assert "areas.git" in capsys.readouterr().err
    assert cli.main(["answers", "check", str(p), "--area", "identity"]) == 0


def test_relative_license_file_resolves_against_project_root(tmp_path: Path):
    meta = tmp_path / ".claude" / "alpha"
    meta.mkdir(parents=True)
    d = valid()
    d["identity"]["license"] = "Custom"
    d["identity"]["license_file"] = "LICENSE.custom"
    path = meta / "project.json"
    path.write_text(json.dumps(d))
    resolved = tmp_path.resolve() / "LICENSE.custom"
    with pytest.raises(AnswersError) as e:
        load_answers(path)
    assert f"identity.license_file: {resolved} does not exist" in str(e.value)
    resolved.write_text("custom")
    assert load_answers(path).identity


@pytest.mark.parametrize("field", ["slug", "name"])
def test_trailing_newline_rejected(tmp_path: Path, field: str):
    d = valid()
    if field == "slug":
        d["identity"]["slug"] = "api\n"
        match = r"identity\.slug"
    else:
        d["components"][0]["name"] = "api\n"
        match = r"components\[0\]\.name"
    with pytest.raises(AnswersError, match=match):
        check(tmp_path, d)
