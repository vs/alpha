import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from helpers import (
    SCENARIOS,
    clone_component,
    generated_repo,
    git,
    install,
    place_answers,
    prove,
    run_cli,
    shell_recipe,
    show_signatures,
)

from alpha import apply, gitops
from alpha.answers import PROJECT_JSON, write_answers
from alpha.apply import PROPOSALS, UPDATE_STATE, Plan, describe
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import GenerateError, load_project_principles
from alpha.gitops import commit_group
from alpha.render.ci import DEPENDABOT, WORKFLOW
from alpha.rendered import find_base

SCENARIO = "web-ts-plus-python-api"
SOURCE = Source(PLUGIN_ROOT, True)
TODAY = date(2026, 11, 2)


def answers(target: Path) -> dict[str, Any]:
    return json.loads((target / PROJECT_JSON).read_text(encoding="utf-8"))


def save(target: Path, data: dict[str, Any]) -> None:
    write_answers(
        target, json.dumps({k: v for k, v in data.items() if k != "installed"})
    )


def plan(target: Path) -> Plan:
    return apply.plan(target, PLUGIN_ROOT, SOURCE, TODAY)


def kinds(p: Plan) -> dict[str, str]:
    return {c.path: c.kind for c in p.changes}


def text_of(p: Plan, path: str) -> str:
    text = next(c.text for c in p.changes if c.path == path)
    assert text is not None
    return text


def commit(target: Path, message: str) -> None:
    git(target, "add", "-A")
    git(target, "commit", "-q", "-m", message)


def add_a_risk_path(data: dict[str, Any]) -> None:
    data["agent_workflow"]["extra_risk_paths"].append("infra/**")


def move_component(data: dict[str, Any], name: str, new: str) -> None:
    old = next(c["path"] for c in data["components"] if c["name"] == name)

    def moved(value: Any) -> Any:
        if isinstance(value, str) and value.startswith(f"{old}/"):
            return f"{new}/{value[len(old) + 1 :]}"
        if isinstance(value, list):
            return [moved(v) for v in cast(list[Any], value)]
        if isinstance(value, dict):
            return {k: moved(v) for k, v in cast(dict[str, Any], value).items()}
        return value

    for key in list(data):
        if key != "overrides":
            data[key] = moved(data[key])
    for c in data["components"]:
        if c["name"] == name:
            c["path"] = new


def remove_component(data: dict[str, Any], name: str) -> None:
    data["components"] = [c for c in data["components"] if c["name"] != name]
    for key, section in data.items():
        if key == "overrides" or not isinstance(section, dict):
            continue
        entries: object = cast(dict[str, Any], section).get("components")
        if isinstance(entries, list):
            kept = [
                e for e in cast(list[dict[str, Any]], entries) if e.get("name") != name
            ]
            section["components"] = kept
            for e in kept:
                calls: object = e.get("calls")
                if isinstance(calls, list):
                    e["calls"] = [c for c in cast(list[str], calls) if c != name]
    data["git"]["scopes"] = [s for s in data["git"]["scopes"] if s != name]
    data["components_talk"] = False


def test_refuses_a_folder_alpha_did_not_generate(tmp_path: Path):
    with pytest.raises(GenerateError, match="Run /alpha:install there first"):
        plan(tmp_path)


def test_update_needs_an_installed_project(tmp_path: Path):
    place_answers(tmp_path, SCENARIO)
    out = run_cli("update", str(tmp_path), env={"ALPHA_SOURCE": str(PLUGIN_ROOT)})
    assert out.returncode == 1
    assert "alpha isn't installed in" in out.stderr and "/alpha:install" in out.stderr


def test_commit_group_sorts_paths_by_what_made_them():
    component_of = {"api/pyproject.toml": "api"}
    assert commit_group("api/pyproject.toml", component_of) == "build:api"
    assert commit_group(WORKFLOW, component_of) == "ci"
    assert commit_group(".github/jactionlint.yaml", component_of) == "ci"
    assert commit_group(DEPENDABOT, component_of) == "dependabot"
    assert commit_group("CLAUDE.md", component_of) == "chore"
    assert commit_group(".claude/settings.json", component_of) == "chore"
    assert commit_group("docs/x.md", component_of) == "docs"
    assert commit_group("README.md", component_of) == "docs"
    for tooling in ("mise.toml", "_typos.toml", "lychee.toml", ".betterleaks.toml"):
        assert commit_group(tooling, component_of) == "tooling"


def test_nothing_to_change_after_generation(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    p = plan(target)
    assert p.changes == ()
    assert describe(p, target) == "alpha update: nothing to change"


def test_invalid_answers_name_the_area_to_revisit(tmp_path: Path, git_env: None):
    generated_repo(tmp_path, SCENARIO)
    data = answers(tmp_path)
    data["components"].append(
        {**data["components"][0], "name": "worker", "path": "worker"}
    )
    data["layout"] = "monorepo"
    save(tmp_path, data)
    with pytest.raises(GenerateError) as err:
        plan(tmp_path)
    assert str(err.value).startswith("Revisit the architecture area:")


def test_answers_that_still_hold_decisions_are_refused(tmp_path: Path, git_env: None):
    generated_repo(tmp_path, SCENARIO)
    data = answers(tmp_path)
    data["decisions"] = [{"area": "git", "title": "x"}]
    (tmp_path / PROJECT_JSON).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(GenerateError, match="decisions: isn't part of the answers"):
        plan(tmp_path)


def test_user_edits_stay_and_the_change_lands(tmp_path: Path, git_env: None):
    """An answer change lands and the user's edit in CLAUDE.md survives."""
    target = generated_repo(tmp_path, SCENARIO)
    claude_md = target / "CLAUDE.md"
    claude_md.write_text(claude_md.read_text() + "Team rule: ask before deploys.\n")
    commit(target, "docs: Add a team rule")
    data = answers(target)
    add_a_risk_path(data)
    data["git"]["scopes"].append("deps")
    save(target, data)
    p = plan(target)
    assert kinds(p)["docs/alpha/principles.toml"] == "change"
    assert kinds(p)["CLAUDE.md"] == "merge"
    apply.write(target, p)
    assert '"infra/**"' in (target / "docs/alpha/principles.toml").read_text()
    text = claude_md.read_text()
    assert text.endswith("Team rule: ask before deploys.\n")
    assert "scopes: api, web, deps," in text


def test_settling_an_open_area_applies_it(tmp_path: Path, git_env: None):
    """An area left open at setup is applied once it is settled."""
    path = place_answers(tmp_path, SCENARIO)
    full = json.loads(path.read_text())
    opened = json.loads(path.read_text())
    opened["areas"]["ui"] = "open"
    del opened["ui"]
    path.write_text(json.dumps(opened))
    install(tmp_path)
    git(tmp_path, "init", "-q", "-b", "main")
    gitops.commit(tmp_path, load_project_principles(tmp_path), [])
    spec = tmp_path / "docs/alpha/specification.md"
    assert "## UI" not in spec.read_text()
    visual = next(
        x
        for x in load_project_principles(tmp_path)["principles"]
        if x["id"] == "visual-system"
    )
    assert visual["active"] is False

    data = answers(tmp_path)
    data["areas"]["ui"] = "done"
    data["ui"] = full["ui"]
    save(tmp_path, data)
    apply.write(tmp_path, plan(tmp_path))

    library = full["ui"]["components"][0]["library"]
    assert library in spec.read_text().split("## UI\n")[1]
    visual = next(
        x
        for x in load_project_principles(tmp_path)["principles"]
        if x["id"] == "visual-system"
    )
    assert visual["active"] is True
    assert "settle the UI" not in spec.read_text()


def test_overlapping_edit_leaves_the_file_and_writes_a_proposal(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    principles = target / "docs/alpha/principles.toml"
    edited = principles.read_text().replace(
        "risk_paths = [", 'risk_paths = ["ops/**", ', 1
    )
    principles.write_text(edited)
    commit(target, "docs: Review smaller batches")
    data = answers(target)
    data["agent_workflow"]["extra_risk_paths"].append("infra/**")
    save(target, data)
    p = plan(target)
    assert kinds(p)["docs/alpha/principles.toml"] == "conflict"
    apply.write(target, p)
    assert principles.read_text() == edited
    assert (
        "<<<<<<< yours"
        in (target / PROPOSALS / "docs/alpha/principles.toml").read_text()
    )
    assert "merge by hand" in describe(p, target)


def test_uncommitted_change_in_a_file_alpha_changes_is_refused(
    tmp_path: Path, git_env: None
):
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


def test_stale_files_are_listed_not_deleted(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    data["releases"]["changelog"] = "none"
    save(target, data)
    p = plan(target)
    assert kinds(p)["CHANGELOG.md"] == "stale"
    apply.write(target, p)
    assert (target / "CHANGELOG.md").is_file()
    assert "stale     CHANGELOG.md" in describe(p, target)


def test_added_component_gets_templates_ci_and_dated_rows(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    clone_component(data, "api", "worker", "worker")
    save(target, data)
    p = plan(target)
    assert p.new_components == ("worker",)
    assert kinds(p)["worker/pyproject.toml"] == "new"
    assert kinds(p)[WORKFLOW] == "change"
    assert "worker" in text_of(p, WORKFLOW)
    rows = text_of(p, "docs/alpha/dependencies.md").splitlines()
    worker = [r for r in rows if r.startswith("| ") and " | worker | " in r]
    api = [r for r in rows if r.startswith("| ") and " | api | " in r]
    assert worker and all(r.endswith("| 2026-11-02 |") for r in worker)
    assert api and all(r.endswith("| 2026-10-19 |") for r in api)
    assert 'name = "worker"' in text_of(p, "docs/alpha/principles.toml")
    assert "alpha bootstrap" in describe(p, target)


def test_new_component_folder_with_uncommitted_files_is_refused(
    tmp_path: Path, git_env: None
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


def test_moved_component_waits_for_its_files(tmp_path: Path, git_env: None):
    generated_repo(tmp_path, SCENARIO)
    data = answers(tmp_path)
    move_component(data, "api", "backend")
    save(tmp_path, data)
    with pytest.raises(GenerateError, match="git mv"):
        plan(tmp_path)


OVERRIDE_ROW = "| observability | loosen | component:api |"


def test_removing_a_component_with_a_scoped_override_plans_cleanly(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    assert data["overrides"][0]["scope"] == "component:api"
    assert OVERRIDE_ROW in (target / "CONTRIBUTING.md").read_text()
    remove_component(data, "api")
    data["architecture"]["contracts"] = {"format": "none", "paths": []}
    save(target, data)
    p = plan(target)
    assert OVERRIDE_ROW in text_of(p, "CONTRIBUTING.md")
    principles = text_of(p, "docs/alpha/principles.toml")
    assert "loosen (component:api)" not in principles
    apply.write(target, p)
    commit_the_update(target)
    data = answers(target)
    add_a_risk_path(data)
    save(target, data)
    assert kinds(plan(target))["docs/alpha/principles.toml"] == "change"


def test_renaming_a_component_leaves_its_override_inert(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    clone_component(data, "api", "backend", "api")
    remove_component(data, "api")
    data["components_talk"] = True
    next(c for c in data["architecture"]["components"] if c["name"] == "web")[
        "calls"
    ] = ["backend"]
    save(target, data)
    p = plan(target)
    assert "loosen (component:api)" not in text_of(p, "docs/alpha/principles.toml")


def test_override_for_a_component_that_never_existed_is_refused(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    data["overrides"].append({**data["overrides"][0], "scope": "component:ghost"})
    save(target, data)
    with pytest.raises(GenerateError, match="there is no component named 'ghost'"):
        plan(target)


def test_moved_component_without_manifests_waits_for_its_files(
    tmp_path: Path, git_env: None
):
    data = json.loads(place_answers(tmp_path, SCENARIO).read_text())
    recipe: dict[str, Any] = {**shell_recipe(), "manifests": []}
    data["recipes"] = {"shell": recipe}
    next(c for c in data["components"] if c["name"] == "api")["stack"] = "shell"
    (tmp_path / PROJECT_JSON).write_text(json.dumps(data))
    prove(tmp_path)
    install(tmp_path)
    gitops.commit(tmp_path, load_project_principles(tmp_path), [])
    assert (tmp_path / "api/tool.cfg").is_file()
    data = answers(tmp_path)
    move_component(data, "api", "backend")
    save(tmp_path, data)
    with pytest.raises(GenerateError, match="git mv"):
        plan(tmp_path)


def test_moved_component_merges_against_its_old_files(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    git(target, "mv", "api", "backend")
    commit(target, "refactor: Move the API to backend")
    data = answers(target)
    move_component(data, "api", "backend")
    save(target, data)
    p = plan(target)
    assert [c.path for c in p.changes if c.kind == "conflict"] == []
    assert kinds(p).get("backend/pyproject.toml") not in ("new", "conflict")
    assert p.changes


def test_update_refuses_while_an_update_awaits_commit(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    principles = target / "docs/alpha/principles.toml"
    principles.write_text(
        principles.read_text().replace("risk_paths = [", 'risk_paths = ["ops/**", ', 1)
    )
    commit(target, "docs: Review smaller batches")
    data = answers(target)
    data["agent_workflow"]["extra_risk_paths"].append("infra/**")
    save(target, data)
    apply.write(target, plan(target))
    with pytest.raises(GenerateError, match="An update is waiting to be committed"):
        plan(target)
    assert (target / UPDATE_STATE).is_file()
    assert (target / PROPOSALS / "docs/alpha/principles.toml").is_file()


def test_update_with_nothing_to_change_writes_nothing(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    before = (target / PROJECT_JSON).read_bytes()
    out = run_cli("update", str(target), env={"ALPHA_SOURCE": str(PLUGIN_ROOT)})
    assert out.returncode == 0, out.stderr
    assert out.stdout == "alpha update: nothing to change\n"
    assert (target / PROJECT_JSON).read_bytes() == before
    assert not (target / UPDATE_STATE).exists()


def test_cli_dry_run_prints_changes_and_writes_nothing(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    add_a_risk_path(data)
    save(target, data)
    out = run_cli(
        "update", str(target), "--dry-run", env={"ALPHA_SOURCE": str(PLUGIN_ROOT)}
    )
    assert out.returncode == 0, out.stderr
    assert "alpha update: 1 file to change" in out.stdout
    assert "--- a/docs/alpha/principles.toml" in out.stdout.splitlines()
    assert git(target, "status", "--porcelain") == f"M {PROJECT_JSON}"


def add_worker(target: Path) -> None:
    data = answers(target)
    clone_component(data, "api", "worker", "worker")
    save(target, data)


def commit_the_update(target: Path) -> tuple[list[str], list[str]]:
    return gitops.commit(target, load_project_principles(target), [])


def test_commit_update_commits_only_alphas_files_in_groups(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    base = git(target, "rev-parse", "HEAD")
    add_worker(target)
    p = plan(target)
    apply.write(target, p)
    (target / "notes.txt").write_text("mine\n")
    hashes, notes = commit_the_update(target)
    subjects = git(target, "log", "--reverse", "--format=%s", f"{base}..HEAD")
    expected = [
        "docs: Update the docs",
        "chore: Update Claude Code rules and settings",
        "build: Pin the repository's check tools",
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
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    base = git(target, "rev-parse", "HEAD")
    (target / UPDATE_STATE).parent.mkdir(parents=True, exist_ok=True)
    (target / "api/extra.txt").write_text("x\n")
    (target / UPDATE_STATE).write_text(
        json.dumps(
            {
                "groups": {"api/extra.txt": "build:api"},
                "new_components": [],
                "conflicts": {},
                "render_tree": git(target, "rev-parse", "HEAD^{tree}"),
            }
        )
    )
    commit_the_update(target)
    subjects = git(target, "log", "--reverse", "--format=%s", f"{base}..HEAD")
    assert subjects.splitlines() == ["build(api): Update toolchain settings"]


def test_commit_update_without_an_update_is_explained(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    with pytest.raises(GenerateError, match="Nothing to commit: run alpha apply"):
        commit_the_update(target)


def test_commit_update_notes_unmerged_conflicts(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    principles = target / "docs/alpha/principles.toml"
    principles.write_text(
        principles.read_text().replace("risk_paths = [", 'risk_paths = ["ops/**", ', 1)
    )
    commit(target, "docs: Review smaller batches")
    data = answers(target)
    data["agent_workflow"]["extra_risk_paths"].append("infra/**")
    save(target, data)
    apply.write(target, plan(target))
    _, notes = commit_the_update(target)
    assert notes == [
        "docs/alpha/principles.toml: alpha's change wasn't merged in (proposal: "
        ".claude/alpha/state/update/docs/alpha/principles.toml)."
    ]


def conflicting_update(target: Path) -> Path:
    principles = target / "docs/alpha/principles.toml"
    principles.write_text(
        principles.read_text().replace("risk_paths = [", 'risk_paths = ["ops/**", ', 1)
    )
    commit(target, "docs: Review smaller batches")
    data = answers(target)
    data["agent_workflow"]["extra_risk_paths"].append("infra/**")
    save(target, data)
    apply.write(target, plan(target))
    return principles


def test_commit_update_keeps_proposals_of_unmerged_conflicts(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    conflicting_update(target)
    commit_the_update(target)
    assert (target / PROPOSALS / "docs/alpha/principles.toml").is_file()
    assert not (target / UPDATE_STATE).exists()


def test_update_state_labels_conflict_digests(tmp_path: Path, git_env: None):
    # The secrets check scans the state folder too, and reads bare hex next
    # to a path like "...-api-keys.md" as a leaked key.
    target = generated_repo(tmp_path, SCENARIO)
    principles = conflicting_update(target)
    state = json.loads((target / UPDATE_STATE).read_text())
    assert state["conflicts"] == {
        "docs/alpha/principles.toml": "sha256:"
        + hashlib.sha256(principles.read_bytes()).hexdigest()
    }


def test_commit_update_deletes_proposals_of_merged_conflicts(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    principles = conflicting_update(target)
    principles.write_text(principles.read_text().replace('"ops/**", ', "", 1))
    _, notes = commit_the_update(target)
    assert not [n for n in notes if "wasn't merged" in n]
    assert not (target / PROPOSALS).exists()


def test_later_update_leaves_an_earlier_kept_proposal(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    conflicting_update(target)
    commit_the_update(target)
    kept = (target / PROPOSALS / "docs/alpha/principles.toml").read_bytes()
    data = answers(target)
    save(target, data)
    apply.write(target, plan(target))
    assert (target / PROPOSALS / "docs/alpha/principles.toml").read_bytes() == kept


def test_commit_update_errors_name_commit_update(
    tmp_path: Path, git_env: None, monkeypatch: pytest.MonkeyPatch
):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    add_a_risk_path(data)
    save(target, data)
    apply.write(target, plan(target))
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.delenv(f"GIT_{role}_NAME")
        monkeypatch.delenv(f"GIT_{role}_EMAIL")
    with pytest.raises(GenerateError) as e:
        commit_the_update(target)
    assert f'"alpha commit {target}"' in str(e.value)


def test_commit_update_new_root_component_commits_alphas_files_and_the_lockfile(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, "python-ml-single")
    principles = load_project_principles(target)
    name = principles["components"][0]["name"]
    (target / "tool.txt").write_text("alpha\n")
    (target / "uv.lock").write_text("version = 1\n")  # as uv sync writes
    (target / "notes.txt").write_text("mine\n")
    (target / UPDATE_STATE).parent.mkdir(parents=True, exist_ok=True)
    (target / UPDATE_STATE).write_text(
        json.dumps(
            {
                "kind": "update",
                "groups": {"tool.txt": f"build:{name}"},
                "new_components": [name],
                "conflicts": {},
                "render_tree": git(target, "rev-parse", "HEAD^{tree}"),
            }
        )
    )
    _, notes = gitops.commit(target, principles, [])
    assert git(target, "status", "--porcelain") == "?? notes.txt"
    assert notes[0] == (
        f"{name} is at the project root, so only alpha's files and its lockfile "
        "were committed; commit any other files its bootstrap made yourself."
    )


def test_commit_update_handles_a_deleted_conflict_file(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    principles = target / "docs/alpha/principles.toml"
    principles.write_text(
        principles.read_text().replace("risk_paths = [", 'risk_paths = ["ops/**", ', 1)
    )
    commit(target, "docs: Review smaller batches")
    data = answers(target)
    data["agent_workflow"]["extra_risk_paths"].append("infra/**")
    save(target, data)
    apply.write(target, plan(target))
    loaded = load_project_principles(target)
    principles.unlink()
    _, notes = gitops.commit(target, loaded, [])
    assert not [n for n in notes if "wasn't merged" in n]
    assert not (target / UPDATE_STATE).exists()


def test_update_refuses_a_project_from_a_newer_alpha(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    data["installed"]["kit_version"] = "99.0.0"
    (target / PROJECT_JSON).write_text(json.dumps(data))
    with pytest.raises(GenerateError, match=r"set up by alpha 99\.0\.0, newer than"):
        plan(target)


def test_update_of_a_current_project_keeps_the_plain_notes(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    (target / "CONTRIBUTING.md").unlink()
    commit(target, "docs: Drop the contributing guide")
    principles = target / "docs/alpha/principles.toml"
    principles.write_text(
        principles.read_text().replace("risk_paths = [", 'risk_paths = ["ops/**", ', 1)
    )
    commit(target, "docs: Review smaller batches")
    add_worker(target)
    commit(target, "chore: Add a worker to the answers")
    data = answers(target)
    data["agent_workflow"]["extra_risk_paths"].append("infra/**")
    save(target, data)
    out = describe(plan(target), target)
    assert (
        "  conflict  docs/alpha/principles.toml (your edits overlap alpha's change: "
        "merge by hand)"
    ) in out
    assert "  skipped   CONTRIBUTING.md (you deleted it: alpha's change to it " in out
    assert "(kit " not in out


def test_a_failed_git_status_says_to_rerun_the_update(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    (target / ".git" / "index").write_bytes(b"not an index")
    data = json.loads((target / ".claude/alpha/project.json").read_text())
    data["git"]["scopes"].append("docs")
    (target / ".claude/alpha/project.json").write_text(json.dumps(data))
    with pytest.raises(GenerateError, match=r'then rerun "alpha apply'):
        apply.plan(target, PLUGIN_ROOT, SOURCE, TODAY)


def test_an_open_design_language_area_can_be_settled_later(
    tmp_path: Path, git_env: None
):
    dest = place_answers(tmp_path, SCENARIO)
    data = json.loads(dest.read_text())
    language = data.pop("design_language")
    data["areas"]["design_language"] = "open"
    dest.write_text(json.dumps(data))
    install(tmp_path)
    git(tmp_path, "init", "-q", "-b", "main")
    gitops.commit(tmp_path, load_project_principles(tmp_path), [])
    assert not (tmp_path / "docs/alpha/design-language.md").exists()
    assert "design language" not in (tmp_path / "CLAUDE.md").read_text().lower()
    assert kinds(plan(tmp_path)) == {}

    data = answers(tmp_path)
    data["design_language"] = language
    data["areas"]["design_language"] = "done"
    save(tmp_path, data)
    p = plan(tmp_path)
    found = kinds(p)
    assert found["docs/alpha/design-language.md"] == "new"
    assert found["docs/alpha/principles.toml"] == "change"
    assert "- **One design language**: " in text_of(p, "CLAUDE.md")
    assert '"docs/alpha/design-language.md"' in text_of(p, "docs/alpha/principles.toml")


def test_R11_1_the_base_survives_a_squash(tmp_path: Path, git_env: None):
    """Squashing alpha's commits with a reset or a squash merge makes a new
    commit that git copies no note to; its tree is the noted commit's."""
    target = generated_repo(tmp_path, SCENARIO)
    start = git(target, "rev-parse", "HEAD")
    data = answers(target)
    add_a_risk_path(data)
    save(target, data)
    apply.write(target, plan(target))
    hashes, _ = commit_the_update(target)
    assert len(hashes) == 2  # the docs and the chore commit
    render = git(target, "rev-parse", "refs/alpha/rendered")
    git(target, "reset", "-q", "--soft", start)
    commit(target, "chore(alpha): Add a risk path")
    head = git(target, "rev-parse", "HEAD")
    assert head not in git(target, "notes", "--ref=alpha-rendered", "list")
    base = find_base(target)
    assert base is not None and base.commit == render
    assert kinds(plan(target)) == {}


def test_R11_1_the_base_is_found_when_git_shows_signatures(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    show_signatures(target, tmp_path_factory.mktemp("keys"))
    git(target, "commit", "-q", "--allow-empty", "-m", "chore: Sign a commit")
    base = find_base(target)
    assert base is not None and "CLAUDE.md" in base.texts


def test_R11_1_the_base_is_the_render_alpha_last_committed(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    head = git(target, "rev-parse", "HEAD")
    render = git(target, "notes", "--ref=alpha-rendered", "show", head)
    assert git(target, "rev-parse", "refs/alpha/rendered") == render
    rendered = git(target, "show", f"{render}:docs/alpha/principles.toml")
    assert rendered == (target / "docs/alpha/principles.toml").read_text().rstrip("\n")
    assert "sha256:" not in (target / PROJECT_JSON).read_text()
    data = answers(target)
    add_a_risk_path(data)
    save(target, data)
    assert kinds(plan(target)) == {"docs/alpha/principles.toml": "change"}


def test_R11_1_a_discarded_update_is_planned_again(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    data = answers(target)
    add_a_risk_path(data)
    save(target, data)
    commit(target, "chore: Add a risk path")
    apply.write(target, plan(target))
    git(target, "checkout", "--", "docs/alpha/principles.toml")
    (target / UPDATE_STATE).unlink()
    assert kinds(plan(target)) == {"docs/alpha/principles.toml": "change"}


def test_R11_1_an_update_ignores_a_render_from_another_branch(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    git(target, "switch", "-q", "-c", "other")
    add_worker(target)
    commit(target, "chore: Add a worker")
    apply.write(target, plan(target))
    commit_the_update(target)
    git(target, "switch", "-q", "main")
    assert kinds(plan(target)) == {}


def test_R11_1_without_a_render_note_differences_become_proposals(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    git(target, "update-ref", "-d", "refs/notes/alpha-rendered")
    claude = target / "CLAUDE.md"
    claude.write_text(claude.read_text() + "Team rule.\n")
    hook = target / ".claude/alpha/hooks/guard_bash.py"
    hook.write_text(hook.read_text() + "# an edit\n")
    commit(target, "docs: Add a team rule")
    found = kinds(plan(target))
    assert found["CLAUDE.md"] == "conflict"
    assert found[".claude/alpha/hooks/guard_bash.py"] == "change"  # alpha's own


def test_R11_2_a_kit_change_merges_and_replaces_alphas_files(
    tmp_path: Path, git_env: None
):
    target = generated_repo(tmp_path, SCENARIO)
    contributing = target / "CONTRIBUTING.md"
    contributing.write_text(contributing.read_text() + "\nOur own section.\n")
    retired = target / ".claude/alpha/hooks/user_prompt_old.py"
    retired.write_text("# a hook an older kit shipped\n")
    hook = target / ".claude/alpha/hooks/guard_bash.py"
    hook.write_text(hook.read_text() + "# as an older kit wrote it\n")
    commit(target, "docs: Add our section")
    data = answers(target)
    data["installed"]["kit_version"] = "0.0.1"
    add_a_risk_path(data)
    (target / PROJECT_JSON).write_text(json.dumps(data))
    commit(target, "chore: As an older kit left it")
    p = plan(target)
    assert p.upgraded_from == "0.0.1"
    found = kinds(p)
    assert found[".claude/alpha/hooks/guard_bash.py"] == "change"
    assert found[".claude/alpha/hooks/user_prompt_old.py"] == "deleted"
    apply.write(target, p)
    assert contributing.read_text().endswith("Our own section.\n")
    assert not retired.exists()
    assert answers(target)["installed"]["kit_version"] != "0.0.1"


def test_R4_1_a_changed_answer_merges_and_keeps_an_edit(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    claude = target / "CLAUDE.md"
    claude.write_text(claude.read_text() + "Team rule.\n")
    commit(target, "docs: Add a team rule")
    data = answers(target)
    data["git"]["scopes"].append("deps")
    save(target, data)
    apply.write(target, plan(target))
    commit_the_update(target)
    assert claude.read_text().endswith("Team rule.\n")
    assert "deps" in claude.read_text()
    assert describe(plan(target), target) == "alpha update: nothing to change"


def test_R4_1_a_new_component_merges_and_keeps_an_edit(tmp_path: Path, git_env: None):
    target = generated_repo(tmp_path, SCENARIO)
    claude = target / "CLAUDE.md"
    claude.write_text(claude.read_text() + "Team rule.\n")
    commit(target, "docs: Add a team rule")
    add_worker(target)
    p = plan(target)
    assert p.new_components == ("worker",)
    apply.write(target, p)
    commit_the_update(target)
    assert (target / "worker/pyproject.toml").is_file()
    assert claude.read_text().endswith("Team rule.\n")
    assert describe(plan(target), target) == "alpha update: nothing to change"


def test_R7_1_settling_areas_writes_their_docs(tmp_path: Path, git_env: None):
    full = json.loads((SCENARIOS / f"{SCENARIO}.json").read_text())

    def open_two(data: dict[str, Any]) -> None:
        for area in ("ui", "performance"):
            data["areas"][area] = "open"
            del data[area]

    target = generated_repo(tmp_path, SCENARIO, open_two)
    spec = target / "docs/alpha/specification.md"
    assert "`/alpha:update UI`" in spec.read_text()
    data = answers(target)
    for area in ("ui", "performance"):
        data["areas"][area] = "done"
        data[area] = full[area]
    save(target, data)
    apply.write(target, plan(target))
    text = spec.read_text()
    assert "## UI" in text and "## Performance" in text
    assert "`/alpha:update UI`" not in text
    assert "`/alpha:update performance`" not in text
    active = {
        p["id"]: p["active"] for p in load_project_principles(target)["principles"]
    }
    assert active["visual-system"] and active["perf-budgets"]


def test_R11_1_the_base_survives_a_rebase(
    tmp_path: Path, git_env: None, monkeypatch: pytest.MonkeyPatch
):
    """CONTRIBUTING.md asks for a rebase before each pull request; the render
    note must move with alpha's commit."""
    target = generated_repo(tmp_path, SCENARIO)
    git(target, "switch", "-q", "-c", "work")
    (target / "notes.md").write_text("x\n")
    git(target, "add", "notes.md")
    git(target, "commit", "-q", "-m", "docs: Add notes")
    before = git(target, "rev-parse", "HEAD~1")
    # Within the same second as the commits, a rebase rewrites them to the
    # same hashes.
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2001-01-01T00:00:00Z")
    git(target, "rebase", "-q", "--root", "--force-rebase")
    assert git(target, "rev-parse", "HEAD~1") != before  # alpha's commit, rewritten
    base = find_base(target)
    assert base is not None and "CLAUDE.md" in base.texts
