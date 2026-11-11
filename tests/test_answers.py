import copy
import io
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from helpers import place_answers, proven, shell_recipe, single_component

from alpha import cli
from alpha.answers import (
    AREAS,
    AnswersError,
    answers_snapshot,
    load_answers,
    parse_answers,
    write_answers,
)
from alpha.validate import area_of, fail

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


def test_component_name_repo_is_reserved(tmp_path: Path):
    d = valid()
    d["components"][1]["name"] = "repo"
    with pytest.raises(AnswersError) as e:
        check(tmp_path, d)
    message = str(e.value)
    assert "components[1].name" in message
    assert "reserved" in message and "repository checks" in message
    assert "another name" in message


@pytest.mark.parametrize(
    "path", ["/abs", "../up", "a/../b", "web/", "./web", "a//b", "a/./b"]
)
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
    single_component(d)
    with pytest.raises(AnswersError, match=r"components\[0\]\.path: .*single.*\"\.\""):
        check(tmp_path, d)
    d["components"][0]["path"] = "."
    assert check(tmp_path, d).layout == "single"


def test_a_stack_without_a_recipe_says_how_to_get_one(tmp_path: Path):
    d = valid()
    d["components"][0]["stack"] = "go"
    with pytest.raises(
        AnswersError,
        match=r'components\[0\]\.stack: "go" has no recipe.*stack-recipe skill.*'
        r"python, rust, typescript",
    ):
        check(tmp_path, d)


def with_shell(d: dict[str, Any]) -> dict[str, Any]:
    comp = dict(d["components"][0], stack="shell", path=".")
    single_component(d, comp)
    d["layout"] = "single"
    d["recipes"] = {"shell": proven(shell_recipe())}
    return d


def test_a_drafted_recipe_makes_its_stack_usable(tmp_path: Path):
    a = check(tmp_path, with_shell(valid()), require_areas=["components"])
    assert a.components[0].stack == "shell"
    assert a.recipes["shell"].proven is False
    assert a.book().get("shell").templates["tests/setup.sh"] == "test 1 -eq 1\n"


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("Rust", "isn't a valid stack name"),
        ("c++", "isn't a valid stack name"),
        ("python", "the kit already has"),
    ],
)
def test_drafted_recipe_names(tmp_path: Path, name: str, problem: str):
    d = with_shell(valid())
    d["recipes"] = {name: shell_recipe()}
    with pytest.raises(AnswersError, match=rf"recipes\.{re.escape(name)}: .*{problem}"):
        check(tmp_path, d, require_areas=["components"])


def test_an_unproven_drafted_recipe_says_it_can_be_removed(tmp_path: Path):
    d = valid()
    d["recipes"] = {"shell": shell_recipe()}
    with pytest.raises(AnswersError, match=r"recipes\.shell: .*or remove it"):
        check(tmp_path, d, require_areas=["components"])


def test_drafted_recipe_errors_name_the_field(tmp_path: Path):
    d = with_shell(valid())
    d["recipes"]["shell"]["commands"]["setup"] = ""
    with pytest.raises(AnswersError, match=r"recipes\.shell\.commands\.setup"):
        check(tmp_path, d, require_areas=["components"])


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


def answers_write(
    target: Path,
    stdin: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[int, str, str]:
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = cli.main(["answers", "write", str(target)])
    out, err = capsys.readouterr()
    return code, out, err


START = {"schema": 1, "areas": dict.fromkeys(AREAS, "pending"), "decisions": []}


def test_answers_write_creates_the_file_and_its_folders(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    code, out, err = answers_write(tmp_path, json.dumps(START), capsys, monkeypatch)
    assert (code, out.strip(), err) == (0, "ok", "")
    saved = tmp_path / ".claude" / "alpha" / "project.json"
    assert json.loads(saved.read_text()) == START
    assert saved.read_text().endswith("}\n")


def test_answers_write_replaces_only_the_keys_it_is_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    answers_write(tmp_path, json.dumps(START), capsys, monkeypatch)
    areas = {**START["areas"], "identity": "in_progress"}
    update = {"areas": areas, "layout": "monorepo"}
    code, _, err = answers_write(tmp_path, json.dumps(update), capsys, monkeypatch)
    assert code == 0, err
    saved = json.loads((tmp_path / ".claude/alpha/project.json").read_text())
    assert saved == {**START, **update}
    assert list(tmp_path.joinpath(".claude/alpha").iterdir()) == [
        tmp_path / ".claude/alpha/project.json"
    ]


@pytest.mark.parametrize(
    ("stdin", "problem", "fix"),
    [
        ("[1, 2]", "a JSON object", "{"),
        ("{", "not valid JSON", "one line in single quotes"),
        ('{"colour": 1}', "colour: unknown key", "allowed keys are"),
        ('{"manifest": {}}', "manifest", "alpha generate"),
    ],
)
def test_answers_write_rejects_bad_input_and_keeps_the_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    stdin: str,
    problem: str,
    fix: str,
):
    answers_write(tmp_path, json.dumps(START), capsys, monkeypatch)
    saved = tmp_path / ".claude/alpha/project.json"
    before = saved.read_text()
    code, out, err = answers_write(tmp_path, stdin, capsys, monkeypatch)
    assert code == 3 and out == ""
    assert problem in err and fix in err
    assert saved.read_text() == before


def test_answers_write_refuses_to_merge_into_a_broken_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    saved = tmp_path / ".claude/alpha/project.json"
    saved.parent.mkdir(parents=True)
    saved.write_text("{oops")
    code, _, err = answers_write(tmp_path, '{"layout": "single"}', capsys, monkeypatch)
    assert code == 3
    assert str(saved) in err and "not valid JSON" in err and "Fix" in err
    assert saved.read_text() == "{oops"


def test_answers_write_keeps_the_old_file_when_the_write_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    answers_write(tmp_path, json.dumps(START), capsys, monkeypatch)
    saved = tmp_path / ".claude/alpha/project.json"
    before = saved.read_text()

    def fail(src: object, dst: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("os.replace", fail)
    code, _, err = answers_write(tmp_path, '{"layout": "single"}', capsys, monkeypatch)
    assert code == 3
    assert "No space left on device" in err and "retry" in err
    assert saved.read_text() == before
    assert list(saved.parent.iterdir()) == [saved]


def test_answers_write_takes_the_object_as_one_argument(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    # A heredoc makes the command multi-line, and Claude Code then prompts
    # even when the alpha CLI is allowed; a one-line --json call matches.
    update = {"schema": 1, "identity": {"target_users": "Editors' desks"}}
    text = json.dumps(update)
    assert cli.main(["answers", "write", str(tmp_path), "--json", text]) == 0
    saved = json.loads((tmp_path / ".claude/alpha/project.json").read_text())
    assert saved == update
    assert capsys.readouterr().out.strip() == "ok"


def test_answers_write_keeps_the_usual_file_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    old = os.umask(0o022)
    try:
        answers_write(tmp_path, json.dumps(START), capsys, monkeypatch)
        saved = tmp_path / ".claude/alpha/project.json"
        assert saved.stat().st_mode & 0o777 == 0o644
        saved.chmod(0o664)
        answers_write(tmp_path, '{"layout": "single"}', capsys, monkeypatch)
        assert saved.stat().st_mode & 0o777 == 0o664
    finally:
        os.umask(old)


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize(
    ("stdin", "problem"),
    [
        (_Terminal(), "no answers given"),
        (
            io.TextIOWrapper(io.BytesIO(b'{"layout": "\xff"}'), encoding="utf-8"),
            "UTF-8",
        ),
    ],
)
def test_answers_write_explains_missing_or_unreadable_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    stdin: io.TextIOBase,
    problem: str,
):
    monkeypatch.setattr("sys.stdin", stdin)
    code = cli.main(["answers", "write", str(tmp_path)])
    out, err = capsys.readouterr()
    assert code == 3 and out == ""
    assert problem in err and "--json" in err
    assert not (tmp_path / ".claude").exists()


@pytest.mark.parametrize("scope", ["Bad Scope", "API", "", "deps/x"])
def test_scope_must_use_commit_scope_syntax(tmp_path: Path, scope: str):
    data = valid()
    data["git"]["scopes"] = ["api", "web", scope]
    with pytest.raises(AnswersError) as err:
        check(tmp_path, data)
    message = str(err.value)
    assert message.startswith(f"git.scopes[2]: {scope!r} can't be a commit scope")
    assert "lowercase letters, digits and hyphens" in message


def test_scopes_may_differ_from_component_names(tmp_path: Path):
    data = valid()
    data["git"]["scopes"] = ["backend", "frontend", "deps"]
    a = check(tmp_path, data)
    assert a.git and a.git.scopes == ("backend", "frontend", "deps")


def test_non_utf8_answers_are_explained(tmp_path: Path):
    path = tmp_path / "project.json"
    path.write_bytes(b'{"schema": 1, "x": "\xff\xfe"}')
    with pytest.raises(AnswersError) as err:
        load_answers(path)
    assert str(err.value).startswith(f"{path}: is not UTF-8 text")
    assert "Save it as UTF-8" in str(err.value)


def test_write_into_non_utf8_answers_is_explained(tmp_path: Path):
    path = tmp_path / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"x": "\xff"}')
    with pytest.raises(AnswersError, match="not valid JSON.*utf-8"):
        write_answers(tmp_path, '{"layout": "single"}')


OLD_AREAS = ("identity", "components", "git", "agent_workflow")


def test_old_interview_without_new_areas_still_loads(tmp_path: Path):
    d = valid()
    d["areas"] = dict.fromkeys(OLD_AREAS, "done")
    for key in ("documentation", "build"):
        del d[key]
    d["decisions"] = [x for x in d["decisions"] if x["area"] in OLD_AREAS]
    a = check(tmp_path, d, require_areas=["identity"])
    assert a.areas["documentation"] == "pending"
    assert a.areas["build"] == "pending"
    assert a.documentation is None and a.build is None


def test_fixture_loads_documentation_and_build():
    a = load_answers(FIXTURE)
    assert a.documentation and a.documentation.external_path == "docs/guide"
    assert a.documentation.mappings[0].docs == ("docs/guide/**",)
    assert a.build and a.build.ci == "github-actions"
    assert [t.name for t in a.build.components] == ["api", "web"]


@pytest.mark.parametrize(
    "path",
    ["guide", "docs", "/docs/guide", "docs/../guide", "docs/guide/", "docs//guide"],
)
def test_external_folder_must_be_under_docs(tmp_path: Path, path: str):
    d = valid()
    d["documentation"]["external_path"] = path
    with pytest.raises(AnswersError, match=r"documentation\.external_path: .*docs/"):
        check(tmp_path, d)


@pytest.mark.parametrize(
    "path",
    ["docs/build.md", "docs/principles.toml", "docs/decisions", "docs/decisions/x"],
)
def test_external_folder_stays_clear_of_generated_docs(tmp_path: Path, path: str):
    d = valid()
    d["documentation"]["external_path"] = path
    for m in d["documentation"]["mappings"]:
        m["docs"] = [f"{path}/**"]
    with pytest.raises(
        AnswersError, match=r"documentation\.external_path: .*alpha writes"
    ):
        check(tmp_path, d)


@pytest.mark.parametrize("field", ["external_path", "mapping"])
def test_paths_with_line_breaks_are_refused(tmp_path: Path, field: str):
    d = valid()
    if field == "external_path":
        d["documentation"]["external_path"] = "docs/gu\nide"
    else:
        d["documentation"]["mappings"][0]["paths"] = ["api/**\n"]
    with pytest.raises(AnswersError, match=r"documentation\."):
        check(tmp_path, d)


def test_external_path_only_with_folder(tmp_path: Path):
    d = valid()
    d["documentation"]["external"] = "readme"
    with pytest.raises(AnswersError, match=r"documentation\.external_path: .*\"\""):
        check(tmp_path, d)
    d["documentation"]["external_path"] = ""
    assert check(tmp_path, d).documentation


def test_elsewhere_needs_a_location(tmp_path: Path):
    d = valid()
    d["documentation"].update(external="elsewhere", external_path="")
    with pytest.raises(AnswersError, match=r"documentation\.external_location: "):
        check(tmp_path, d)
    d["documentation"]["external_location"] = "https://wiki.example.com/pico"
    assert check(tmp_path, d).documentation


def test_bad_external_lists_choices(tmp_path: Path):
    d = valid()
    d["documentation"]["external"] = "wiki"
    with pytest.raises(AnswersError, match=r"external: .*elsewhere, folder"):
        check(tmp_path, d)


@pytest.mark.parametrize("field", ["paths", "docs"])
@pytest.mark.parametrize(
    "value",
    [[], ["/abs/**"], ["a/../b"], [""], "docs/x.md", ["web/pages/"], ["./api/**"]]
    + [["api//routes/**"]],
)
def test_mapping_paths_and_docs_rules(tmp_path: Path, field: str, value: object):
    d = valid()
    d["documentation"]["mappings"][0][field] = value
    with pytest.raises(AnswersError, match=rf"mappings\[0\]\.{field}"):
        check(tmp_path, d)


def test_ci_none_needs_a_loosening_override(tmp_path: Path):
    d = valid()
    d["build"]["ci"] = "none"
    with pytest.raises(AnswersError, match=r"build\.ci: .*build-hosting-upfront"):
        check(tmp_path, d)
    d["overrides"].append(
        {
            "principle": "build-hosting-upfront",
            "scope": "project",
            "change": "loosen",
            "params": {},
            "reason": "A throwaway prototype with no shared repository.",
        }
    )
    b = check(tmp_path, d).build
    assert b and b.ci == "none"


def test_build_components_must_match_components(tmp_path: Path):
    d = valid()
    d["build"]["components"].pop()
    with pytest.raises(AnswersError, match=r"build\.components: no entry for .*'web'"):
        check(tmp_path, d)
    d = valid()
    d["build"]["components"].append({"name": "x", "artifact": "none", "hosting": ""})
    with pytest.raises(
        AnswersError, match=r"build\.components\[2\]\.name: .*'x'.*api, web"
    ):
        check(tmp_path, d)


def test_deployed_component_needs_hosting_and_an_environment(tmp_path: Path):
    d = valid()
    d["build"]["components"][1]["hosting"] = " "
    with pytest.raises(AnswersError, match=r"build\.components\[1\]\.hosting: "):
        check(tmp_path, d)
    d = valid()
    d["build"]["environments"] = []
    with pytest.raises(AnswersError, match=r"build\.environments: .*production"):
        check(tmp_path, d)
    d["build"]["environments"] = ["Prod!"]
    with pytest.raises(AnswersError, match=r"build\.environments\[0\]: "):
        check(tmp_path, d)


def test_bad_artifact_lists_choices(tmp_path: Path):
    d = valid()
    d["build"]["components"][0]["artifact"] = "zip"
    with pytest.raises(
        AnswersError, match=r"build\.components\[0\]\.artifact: .*container"
    ):
        check(tmp_path, d)


def test_area_of_maps_fields_to_their_area():
    assert area_of("testing.components[1].levels") == "testing"
    assert area_of("agent_workflow.max_lines") == "agent_workflow"
    for where in (
        "layout",
        "components_talk",
        "components[0].path",
        "recipes.rust.commands",
    ):
        assert area_of(where) == "components"
    for where in ("decisions", "overrides[0].principle", "schema", ""):
        assert area_of(where) is None


def test_fail_keeps_where():
    assert fail("ui.components", "is wrong", "Fix it").where == "ui.components"


def test_parse_answers_matches_load_answers(tmp_path: Path):
    path = place_answers(tmp_path, "web-ts-plus-python-api")
    top = json.loads(path.read_text())
    assert parse_answers(top, tmp_path) == load_answers(path)


def test_snapshot_leaves_out_the_manifest():
    top = {"schema": 1, "manifest": {"files": {}}, "decisions": [{"area": "git"}]}
    snap = answers_snapshot(top)
    assert snap == {"schema": 1, "decisions": [{"area": "git"}]}
    snap["decisions"].append({})
    assert len(top["decisions"]) == 1
