import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from helpers import (
    clone_component,
    generated_repo,
    git,
    place_answers,
    run_cli,
)

from alpha.answers import PROJECT_JSON, answers_snapshot, write_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import GenerateError, load_project_principles
from alpha.gitops import commit_group, commit_update
from alpha.render.ci import DEPENDABOT, WORKFLOW
from alpha.update import (
    PROPOSALS,
    UPDATE_STATE,
    UpdatePlan,
    apply_update,
    describe,
    plan_update,
)

SCENARIO = "web-ts-plus-python-api"
SOURCE = Source(PLUGIN_ROOT, True, "")
TODAY = date(2026, 11, 2)
DECISION = {
    "area": "agent_workflow",
    "title": "Smaller review batches",
    "context": "Reviews of 200 lines took too long to read well.",
    "decision": "Review at most 120 changed lines at a time.",
    "consequences": "More reviews, each one shorter.",
}


def answers(target: Path) -> dict[str, Any]:
    return json.loads((target / PROJECT_JSON).read_text(encoding="utf-8"))


def save(target: Path, data: dict[str, Any]) -> None:
    """Write every key but the manifest back, as the interview's skills do."""
    write_answers(target, json.dumps(answers_snapshot(data)))


def plan(target: Path) -> UpdatePlan:
    return plan_update(target, SOURCE, TODAY)


def kinds(p: UpdatePlan) -> dict[str, str]:
    return {c.path: c.kind for c in p.changes}


def text_of(p: UpdatePlan, path: str) -> str:
    text = next(c.text for c in p.changes if c.path == path)
    assert text is not None
    return text


def commit(target: Path, message: str) -> None:
    git(target, "add", "-A")
    git(target, "commit", "-q", "-m", message)


def smaller_reviews(data: dict[str, Any]) -> None:
    data["agent_workflow"]["max_lines"] = 120
    data["decisions"].append(dict(DECISION))


def move_component(data: dict[str, Any], name: str, new: str) -> None:
    """Give a component a new folder in every area (decisions stay history)."""
    old = next(c["path"] for c in data["components"] if c["name"] == name)

    def moved(value: Any) -> Any:
        if isinstance(value, str) and value.startswith(f"{old}/"):
            return f"{new}/{value[len(old) + 1 :]}"
        if isinstance(value, list):
            return [moved(v) for v in value]
        if isinstance(value, dict):
            return {k: moved(v) for k, v in value.items()}
        return value

    for key in list(data):
        if key not in ("decisions", "overrides", "manifest"):
            data[key] = moved(data[key])
    for c in data["components"]:
        if c["name"] == name:
            c["path"] = new


def remove_component(data: dict[str, Any], name: str) -> None:
    """Drop a component from every area (decisions and overrides stay history)."""
    data["components"] = [c for c in data["components"] if c["name"] != name]
    for key, section in data.items():
        if key in ("decisions", "overrides", "manifest") or not isinstance(
            section, dict
        ):
            continue
        entries = section.get("components")
        if isinstance(entries, list):
            section["components"] = [
                e
                for e in entries
                if not (isinstance(e, dict) and e.get("name") == name)
            ]
            for e in section["components"]:
                if isinstance(e, dict) and isinstance(e.get("calls"), list):
                    e["calls"] = [c for c in e["calls"] if c != name]
    data["git"]["scopes"] = [s for s in data["git"]["scopes"] if s != name]
    data["components_talk"] = False


def test_refuses_a_folder_alpha_did_not_generate(tmp_path: Path):
    with pytest.raises(GenerateError, match="out of scope"):
        plan(tmp_path)


def test_unfinished_interview_points_to_new_project(tmp_path: Path):
    place_answers(tmp_path, SCENARIO)
    with pytest.raises(GenerateError, match="/alpha:new-project"):
        plan(tmp_path)


def test_refuses_a_project_without_applied_answers(tmp_path: Path, generate_scenario):
    generate_scenario(tmp_path, SCENARIO)
    data = answers(tmp_path)
    del data["manifest"]["applied"]
    (tmp_path / PROJECT_JSON).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(GenerateError, match="generated before alpha kept") as err:
        plan(tmp_path)
    assert str(err.value).endswith(
        "Instead, make the change by hand, and record it with the project's "
        "/decision skill."
    )


def test_baseline_that_no_longer_loads_names_the_alpha_to_use(
    tmp_path: Path, generate_scenario
):
    generate_scenario(tmp_path, SCENARIO)
    data = answers(tmp_path)
    data["manifest"]["applied"]["schema"] = 2  # as a later alpha might write
    (tmp_path / PROJECT_JSON).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(GenerateError) as err:
        plan(tmp_path)
    defaults = data["manifest"]["defaults"]["path"]
    message = str(err.value)
    assert f"generated by alpha {data['manifest']['kit_version']}" in message
    assert f"ALPHA_SOURCE={defaults} alpha update {tmp_path}" in message
    assert message.endswith(
        "with that alpha, or make the change by hand, and record it with the "
        "project's /decision skill."
    )


def test_commit_group_sorts_paths_by_what_made_them():
    component_of = {"api/pyproject.toml": "api"}
    assert commit_group("api/pyproject.toml", component_of) == "build:api"
    assert commit_group(WORKFLOW, component_of) == "ci"
    assert commit_group(DEPENDABOT, component_of) == "dependabot"
    assert commit_group("CLAUDE.md", component_of) == "chore"
    assert commit_group(".claude/settings.json", component_of) == "chore"
    assert commit_group("docs/x.md", component_of) == "docs"
    assert commit_group("README.md", component_of) == "docs"


def test_nothing_to_change_after_generation(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    p = plan(target)
    assert p.changes == ()
    assert describe(p, target) == "alpha update: nothing to change"


def test_invalid_answers_name_the_area_to_revisit(tmp_path: Path, generate_scenario):
    generate_scenario(tmp_path, SCENARIO)
    data = answers(tmp_path)
    data["components"].append(
        {**data["components"][0], "name": "worker", "path": "worker"}
    )
    data["layout"] = "monorepo"
    save(tmp_path, data)
    with pytest.raises(GenerateError) as err:
        plan(tmp_path)
    assert str(err.value).startswith("Revisit the architecture area:")


def test_changed_decision_is_refused(tmp_path: Path, generate_scenario):
    generate_scenario(tmp_path, SCENARIO)
    data = answers(tmp_path)
    data["decisions"][0]["title"] = "A better title"
    save(tmp_path, data)
    with pytest.raises(GenerateError, match=r"decisions\[0\] changed"):
        plan(tmp_path)


def test_user_edits_stay_and_the_change_lands(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    claude_md = target / "CLAUDE.md"
    claude_md.write_text(claude_md.read_text() + "Team rule: ask before deploys.\n")
    commit(target, "docs: Add a team rule")
    data = answers(target)
    smaller_reviews(data)
    data["git"]["scopes"].append("deps")  # CLAUDE.md lists the scopes
    save(target, data)
    p = plan(target)
    assert kinds(p)["docs/principles.toml"] == "change"
    assert kinds(p)["CLAUDE.md"] == "merge"
    apply_update(target, p)
    assert "max_lines = 120\n" in (target / "docs/principles.toml").read_text()
    text = claude_md.read_text()
    assert text.endswith("Team rule: ask before deploys.\n")
    assert "scopes: api, web, deps," in text


def test_new_decision_is_numbered_after_the_projects_own_records(
    tmp_path: Path, git_env
):
    target = generated_repo(tmp_path, SCENARIO)
    records = target / "docs" / "decisions"
    (records / "0020-use-sqlite.md").write_text("# 0020. Use SQLite\n")
    commit(target, "docs: Record the SQLite decision")
    earlier = {p.name: p.read_bytes() for p in records.iterdir()}
    data = answers(target)
    data["decisions"].append(dict(DECISION))
    save(target, data)
    p = plan(target)
    new = "docs/decisions/0021-smaller-review-batches.md"
    assert kinds(p)[new] == "new"
    apply_update(target, p)
    assert "Date: 2026-11-02\n" in (target / new).read_text()
    assert {
        name: path.read_bytes()
        for name, path in ((p.name, p) for p in records.iterdir())
        if name in earlier
    } == earlier


def test_overlapping_edit_leaves_the_file_and_writes_a_proposal(
    tmp_path: Path, git_env
):
    target = generated_repo(tmp_path, SCENARIO)
    principles = target / "docs/principles.toml"
    edited = principles.read_text().replace("max_lines = 200\n", "max_lines = 150\n")
    principles.write_text(edited)
    commit(target, "docs: Review smaller batches")
    data = answers(target)
    data["agent_workflow"]["max_lines"] = 120
    save(target, data)
    p = plan(target)
    assert kinds(p)["docs/principles.toml"] == "conflict"
    apply_update(target, p)
    assert principles.read_text() == edited
    assert "<<<<<<< yours" in (target / PROPOSALS / "docs/principles.toml").read_text()
    assert "merge by hand" in describe(p, target)


def test_uncommitted_change_in_a_file_alpha_changes_is_refused(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    claude_md = target / "CLAUDE.md"
    claude_md.write_text(claude_md.read_text() + "Draft rule.\n")
    data = answers(target)
    data["git"]["scopes"].append("deps")
    save(target, data)
    with pytest.raises(GenerateError) as err:
        plan(target)
    assert "CLAUDE.md" in str(err.value)
    assert "Commit or stash" in str(err.value)


def test_stale_files_are_listed_not_deleted(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    data["releases"]["changelog"] = "none"
    data["decisions"].append({**DECISION, "area": "releases", "title": "No changelog"})
    save(target, data)
    p = plan(target)
    assert kinds(p)["CHANGELOG.md"] == "stale"
    apply_update(target, p)
    assert (target / "CHANGELOG.md").is_file()
    assert "stale     CHANGELOG.md" in describe(p, target)


def test_added_component_gets_templates_ci_and_dated_rows(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    clone_component(data, "api", "worker", "worker")
    data["decisions"].append(
        {**DECISION, "area": "components", "title": "Add a worker"}
    )
    save(target, data)
    p = plan(target)
    assert p.new_components == ("worker",)
    assert kinds(p)["worker/pyproject.toml"] == "new"
    assert kinds(p)[WORKFLOW] == "change"
    assert "worker" in text_of(p, WORKFLOW)
    rows = text_of(p, "docs/dependencies.md").splitlines()
    worker = [r for r in rows if r.startswith("| ") and " | worker | " in r]
    api = [r for r in rows if r.startswith("| ") and " | api | " in r]
    assert worker and all(r.endswith("| 2026-11-02 |") for r in worker)
    assert api and all(r.endswith("| 2026-10-19 |") for r in api)
    assert 'name = "worker"' in text_of(p, "docs/principles.toml")
    assert "alpha bootstrap" in describe(p, target)


def test_new_component_folder_with_uncommitted_files_is_refused(
    tmp_path: Path, git_env
):
    target = generated_repo(tmp_path, SCENARIO)
    (target / "worker").mkdir()
    (target / "worker/notes.txt").write_text("mine\n")
    add_worker(target)
    with pytest.raises(GenerateError) as err:
        plan(target)
    assert str(err.value) == (
        "Commit or move your files in worker/ first (worker/notes.txt), then "
        f"run alpha update {target} again."
    )


def test_moved_component_waits_for_its_files(tmp_path: Path, generate_scenario):
    generate_scenario(tmp_path, SCENARIO)
    data = answers(tmp_path)
    move_component(data, "api", "backend")
    save(tmp_path, data)
    with pytest.raises(GenerateError, match="git mv"):
        plan(tmp_path)


OVERRIDE_RECORD = "docs/decisions/0018-override-observability.md"


def test_removing_a_component_with_a_scoped_override_plans_cleanly(
    tmp_path: Path, git_env
):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    assert data["overrides"][0]["scope"] == "component:api"
    assert OVERRIDE_RECORD in (target / "docs/principles.toml").read_text()
    remove_component(data, "api")
    data["architecture"]["contracts"] = {"format": "none", "paths": []}
    data["decisions"].append({**DECISION, "area": "components", "title": "Drop api"})
    save(target, data)
    p = plan(target)
    assert OVERRIDE_RECORD not in kinds(p)  # its record stays, at the same number
    principles = text_of(p, "docs/principles.toml")
    assert OVERRIDE_RECORD not in principles  # inert: it changes no principle
    apply_update(target, p)
    commit_the_update(target)
    # The new baseline has no api either; the override still loads.
    data = answers(target)
    smaller_reviews(data)
    save(target, data)
    assert kinds(plan(target))["docs/principles.toml"] == "change"


def test_renaming_a_component_leaves_its_override_inert(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    clone_component(data, "api", "backend", "api")
    remove_component(data, "api")
    data["components_talk"] = True
    next(c for c in data["architecture"]["components"] if c["name"] == "web")[
        "calls"
    ] = ["backend"]
    data["decisions"].append(
        {**DECISION, "area": "components", "title": "Rename api to backend"}
    )
    save(target, data)
    p = plan(target)
    assert OVERRIDE_RECORD not in kinds(p)
    assert OVERRIDE_RECORD not in text_of(p, "docs/principles.toml")


def test_override_for_a_component_that_never_existed_is_refused(
    tmp_path: Path, git_env
):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    data["overrides"].append({**data["overrides"][0], "scope": "component:ghost"})
    save(target, data)
    with pytest.raises(GenerateError, match="there is no component named 'ghost'"):
        plan(target)


def test_moved_component_merges_against_its_old_files(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    git(target, "mv", "api", "backend")
    commit(target, "refactor: Move the API to backend")
    data = answers(target)
    move_component(data, "api", "backend")
    data["decisions"].append(
        {**DECISION, "area": "components", "title": "Move the API to backend"}
    )
    save(target, data)
    p = plan(target)
    assert [c.path for c in p.changes if c.kind == "conflict"] == []
    assert kinds(p).get("backend/pyproject.toml") not in ("new", "conflict")
    assert p.changes  # the docs and CI follow the new folder


def test_applied_update_becomes_the_new_baseline(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    smaller_reviews(data)
    save(target, data)
    apply_update(target, plan(target))
    after = answers(target)
    assert after["manifest"]["applied"] == answers_snapshot(after)
    assert after["manifest"]["updated_at"] == "2026-11-02"
    state = json.loads((target / UPDATE_STATE).read_text())
    assert "before_tree" in state
    assert state["groups"]["docs/principles.toml"] == "docs"
    (target / UPDATE_STATE).unlink()  # as commit-update does when it's done
    assert describe(plan(target), target) == "alpha update: nothing to change"


def test_update_refuses_while_an_update_awaits_commit(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    principles = target / "docs/principles.toml"
    principles.write_text(
        principles.read_text().replace("max_lines = 200\n", "max_lines = 150\n")
    )
    commit(target, "docs: Review smaller batches")
    data = answers(target)
    data["agent_workflow"]["max_lines"] = 120
    save(target, data)
    apply_update(target, plan(target))
    with pytest.raises(GenerateError, match="An update is waiting to be committed"):
        plan(target)
    assert (target / UPDATE_STATE).is_file()
    assert (target / PROPOSALS / "docs/principles.toml").is_file()


def test_update_with_nothing_to_change_writes_nothing(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    before = (target / PROJECT_JSON).read_bytes()
    out = run_cli("update", str(target), env={"ALPHA_SOURCE": str(PLUGIN_ROOT)})
    assert out.returncode == 0, out.stderr
    assert out.stdout == "alpha update: nothing to change\n"
    assert (target / PROJECT_JSON).read_bytes() == before
    assert not (target / UPDATE_STATE).exists()


def test_cli_dry_run_prints_changes_and_writes_nothing(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    smaller_reviews(data)
    save(target, data)
    out = run_cli(
        "update", str(target), "--dry-run", env={"ALPHA_SOURCE": str(PLUGIN_ROOT)}
    )
    assert out.returncode == 0, out.stderr
    assert "files to change" in out.stdout
    assert "--- a/docs/principles.toml" in out.stdout.splitlines()
    assert git(target, "status", "--porcelain") == f"M {PROJECT_JSON}"


def add_worker(target: Path) -> None:
    data = answers(target)
    clone_component(data, "api", "worker", "worker")
    data["decisions"].append(
        {**DECISION, "area": "components", "title": "Add a worker"}
    )
    save(target, data)


def commit_the_update(target: Path) -> tuple[list[str], list[str]]:
    return commit_update(target, load_project_principles(target), [])


def test_commit_update_commits_only_alphas_files_in_groups(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    base = git(target, "rev-parse", "HEAD")
    add_worker(target)
    p = plan(target)
    apply_update(target, p)
    (target / "notes.txt").write_text("mine\n")
    hashes, notes = commit_the_update(target)
    subjects = git(target, "log", "--reverse", "--format=%s", f"{base}..HEAD")
    expected = [
        "docs: Update docs and decision records",
        "chore: Update Claude Code rules and settings",
        "build(worker): Set up python toolchain and tests",
        "ci: Update the CI checks",
    ]
    if DEPENDABOT in p.groups:
        expected.append("ci: Update the dependency update schedule")
    assert subjects.splitlines() == expected
    assert len(hashes) == len(expected)
    assert notes == []
    assert git(target, "status", "--porcelain") == "?? notes.txt"
    assert not (target / UPDATE_STATE).exists()
    assert not (target / PROPOSALS).exists()


def test_commit_update_names_an_existing_components_changed_templates(
    tmp_path: Path, git_env
):
    target = generated_repo(tmp_path, SCENARIO)
    base = git(target, "rev-parse", "HEAD")
    (target / UPDATE_STATE).parent.mkdir(parents=True, exist_ok=True)
    (target / "api/extra.txt").write_text("x\n")
    (target / UPDATE_STATE).write_text(
        json.dumps(
            {
                "before_tree": None,
                "groups": {"api/extra.txt": "build:api"},
                "new_components": [],
                "conflicts": {},
            }
        )
    )
    commit_the_update(target)
    subjects = git(target, "log", "--reverse", "--format=%s", f"{base}..HEAD")
    assert subjects.splitlines() == ["build(api): Update toolchain settings"]


def test_commit_update_with_only_the_manifest_commits_it_and_clears_state(
    tmp_path: Path, git_env
):
    target = generated_repo(tmp_path, SCENARIO)
    base = git(target, "rev-parse", "HEAD")
    p = plan(target)
    (target / PROJECT_JSON).write_text(
        (target / PROJECT_JSON).read_text().replace("\n}\n", ',\n  "note": 1\n}\n')
    )
    apply_update(target, p)  # no changes: only the manifest moves
    assert (target / UPDATE_STATE).is_file()
    hashes, notes = commit_the_update(target)
    subjects = git(target, "log", "--format=%s", f"{base}..HEAD")
    assert subjects.splitlines() == ["chore: Update Claude Code rules and settings"]
    assert len(hashes) == 1 and notes == []
    assert git(target, "status", "--porcelain") == ""
    assert not (target / UPDATE_STATE).exists()


def test_commit_update_without_an_update_is_explained(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    with pytest.raises(GenerateError, match="Nothing to commit: run alpha update"):
        commit_the_update(target)


def test_commit_update_notes_unmerged_conflicts(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    principles = target / "docs/principles.toml"
    principles.write_text(
        principles.read_text().replace("max_lines = 200\n", "max_lines = 150\n")
    )
    commit(target, "docs: Review smaller batches")
    data = answers(target)
    data["agent_workflow"]["max_lines"] = 120
    data["decisions"].append(dict(DECISION))
    save(target, data)
    apply_update(target, plan(target))
    _, notes = commit_the_update(target)
    assert notes == [
        "docs/principles.toml: alpha's change wasn't merged in (proposal: "
        ".claude/alpha/state/update/docs/principles.toml)."
    ]


def conflicting_update(target: Path) -> Path:
    """Edit max_lines by hand, then change it in the answers: a conflict."""
    principles = target / "docs/principles.toml"
    principles.write_text(
        principles.read_text().replace("max_lines = 200\n", "max_lines = 150\n")
    )
    commit(target, "docs: Review smaller batches")
    data = answers(target)
    data["agent_workflow"]["max_lines"] = 120
    data["decisions"].append(dict(DECISION))
    save(target, data)
    apply_update(target, plan(target))
    return principles


def test_commit_update_keeps_proposals_of_unmerged_conflicts(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    conflicting_update(target)
    commit_the_update(target)
    # The baseline moved on, so alpha won't propose the change again.
    assert (target / PROPOSALS / "docs/principles.toml").is_file()
    assert not (target / UPDATE_STATE).exists()


def test_commit_update_deletes_proposals_of_merged_conflicts(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    principles = conflicting_update(target)
    principles.write_text(principles.read_text().replace("150", "120"))
    _, notes = commit_the_update(target)
    assert not [n for n in notes if "wasn't merged" in n]
    assert not (target / PROPOSALS).exists()


def test_later_update_leaves_an_earlier_kept_proposal(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    conflicting_update(target)
    commit_the_update(target)
    kept = (target / PROPOSALS / "docs/principles.toml").read_bytes()
    data = answers(target)
    data["decisions"].append({**DECISION, "title": "Another decision"})
    save(target, data)
    apply_update(target, plan(target))
    assert (target / PROPOSALS / "docs/principles.toml").read_bytes() == kept


def test_apply_update_absorbs_alphas_changes_into_review(
    tmp_path: Path, git_env, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.syspath_prepend(str(PLUGIN_ROOT / "project-files/hooks"))
    import review

    target = generated_repo(tmp_path, SCENARIO)
    review.ensure_state(target)  # reviewed at HEAD, before the answers change
    add_worker(target)
    # A Stop can come before commit-update (the skill asks about stale files).
    assert apply_update(target, plan(target)) == []
    debt = review.debt(target, load_project_principles(target))
    assert debt["files"] == [PROJECT_JSON]  # the answers edit is the user's debt
    _, notes = commit_the_update(target)
    assert notes == []


def test_absorb_leaves_edits_after_the_update_as_debt(
    tmp_path: Path, git_env, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.syspath_prepend(str(PLUGIN_ROOT / "project-files/hooks"))
    import review

    target = generated_repo(tmp_path, SCENARIO)
    review.ensure_state(target)
    add_worker(target)
    apply_update(target, plan(target))
    (target / "api/app_code.py").write_text("x = 1\n")
    debt = review.debt(target, load_project_principles(target))
    assert "api/app_code.py" in debt["files"]
    assert "worker/pyproject.toml" not in debt["files"]


FAILING_ABSORB = """\
import runpy, sys
from pathlib import Path
if sys.argv[1:2] == ["absorb"]:
    sys.exit(1)
runpy.run_path(str(Path(__file__).with_name("review_real.py")), run_name="__main__")
"""


def test_cli_update_says_the_reviewer_will_look_when_absorb_fails(
    tmp_path: Path, git_env
):
    target = generated_repo(tmp_path, SCENARIO)
    hooks = target / ".claude/alpha/hooks"
    (hooks / "review.py").rename(hooks / "review_real.py")
    (hooks / "review.py").write_text(FAILING_ABSORB)
    data = answers(target)
    smaller_reviews(data)
    save(target, data)
    out = run_cli("update", str(target), env={"ALPHA_SOURCE": str(PLUGIN_ROOT)})
    assert out.returncode == 0, out.stderr
    state = json.loads((target / UPDATE_STATE).read_text())
    assert state["before_tree"] and state["after_tree"]  # snapshots still ran
    assert out.stdout.splitlines()[-1] == (
        "The reviewer will look at alpha's changes at the next Stop."
    )


def test_commit_update_errors_name_commit_update(
    tmp_path: Path, git_env, monkeypatch: pytest.MonkeyPatch
):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    smaller_reviews(data)
    save(target, data)
    apply_update(target, plan(target))
    for role in ("AUTHOR", "COMMITTER"):  # no identity left anywhere
        monkeypatch.delenv(f"GIT_{role}_NAME")
        monkeypatch.delenv(f"GIT_{role}_EMAIL")
    with pytest.raises(GenerateError) as e:
        commit_the_update(target)
    assert f'"alpha commit-update {target}"' in str(e.value)
    assert "commit-skeleton" not in str(e.value)


def test_commit_update_new_root_component_commits_only_alphas_files(
    tmp_path: Path, git_env
):
    # A root component can't be added next to others (folders may not nest), so
    # the state is written as alpha update would leave it for a lone root one.
    target = generated_repo(tmp_path, "python-ml-single")
    principles = load_project_principles(target)
    name = principles["components"][0]["name"]
    (target / "tool.txt").write_text("alpha\n")
    (target / "notes.txt").write_text("mine\n")
    (target / UPDATE_STATE).parent.mkdir(parents=True, exist_ok=True)
    (target / UPDATE_STATE).write_text(
        json.dumps(
            {
                "before_tree": None,
                "groups": {"tool.txt": f"build:{name}"},
                "new_components": [name],
                "conflicts": {},
            }
        )
    )
    _, notes = commit_update(target, principles, [])
    assert git(target, "status", "--porcelain") == "?? notes.txt"
    assert notes[0] == (
        f"{name} is at the project root, so only alpha's files were committed; "
        "commit any files its bootstrap made (such as lockfiles) yourself."
    )


def test_commit_update_handles_a_deleted_conflict_file(tmp_path: Path, git_env):
    target = generated_repo(tmp_path, SCENARIO)
    principles = target / "docs/principles.toml"
    principles.write_text(
        principles.read_text().replace("max_lines = 200\n", "max_lines = 150\n")
    )
    commit(target, "docs: Review smaller batches")
    data = answers(target)
    data["agent_workflow"]["max_lines"] = 120
    data["decisions"].append(dict(DECISION))
    save(target, data)
    apply_update(target, plan(target))
    loaded = load_project_principles(target)
    principles.unlink()  # the user resolved the conflict by deleting the file
    _, notes = commit_update(target, loaded, [])
    assert not [n for n in notes if "wasn't merged" in n]  # nothing to hash
    assert not (target / UPDATE_STATE).exists()
