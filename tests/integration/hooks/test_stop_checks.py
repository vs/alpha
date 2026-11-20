import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any

import _common
import pytest
import review
import stop_checks
import untested

from .conftest import HOOKS, STUB, Project

FAIL = "python3 -c \"import sys; print('boom'); sys.exit(1)\""
PAYLOAD: dict[str, Any] = {"hook_event_name": "Stop", "stop_hook_active": False}
AWS_KEY = "AKIA" + "A" * 16
PASSWORD = "hunter2" * 2


EVERY_STEP = tuple(stop_checks.COMMAND_PRINCIPLES)


def marker_cmd(name: str) -> str:
    return f"python3 -c \"open('{name}', 'a').write('x')\""


def commit_all(project: Project) -> None:
    project.git("add", "-A")
    project.git("commit", "-q", "-m", "chore: Baseline")


def run(project: Project) -> subprocess.CompletedProcess[str]:
    return project.run_hook("stop_checks.py", PAYLOAD)


def reason(proc: subprocess.CompletedProcess[str]) -> str:
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["decision"] == "block"
    return out["reason"]


def counter(project: Project) -> int:
    path = project.root / ".claude" / "alpha" / "state" / "stop-blocks"
    return json.loads(path.read_text())["count"] if path.exists() else 0


def test_secret_in_new_file_blocks_without_value(project: Project) -> None:
    commit_all(project)
    project.write("notes.txt", f"one\ntwo\nkey = {AWS_KEY}\n")
    text = reason(run(project))
    assert text.startswith("alpha checks before stopping:\n1. ")
    assert "notes.txt:3" in text
    assert "move it to the environment and reference it by name" in text
    assert AWS_KEY not in text


def test_secret_in_added_line_of_tracked_file(project: Project) -> None:
    project.write("a.txt", "x\n")
    commit_all(project)
    project.write("a.txt", f"x\npassword = '{PASSWORD}'\n")
    text = reason(run(project))
    assert "a.txt:2" in text
    assert "hunter2" not in text


def test_secret_without_any_commit(project: Project) -> None:
    project.write("a.txt", f"x\n{AWS_KEY}\n")
    assert "a.txt:2" in reason(run(project))


def test_binary_and_state_files_are_not_scanned(project: Project) -> None:
    commit_all(project)
    (project.root / "blob.bin").write_bytes(b"\0" + AWS_KEY.encode())
    project.write(".claude/alpha/state/x", AWS_KEY)
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""


def test_source_without_tests_blocks(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    text = reason(run(project))
    assert "api: source changed (api/src/app.py) but no tests changed." in text
    assert "Principle tests-first-class: add or update tests." in text


def run_untested(project: Project, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOKS / "untested.py"), *args],
        cwd=project.root,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project.root)},
        capture_output=True,
        text=True,
    )


def test_R12_6_an_untested_note_holds_until_the_file_changes(
    project: Project,
) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    assert "If a file needs none (a rename, a constant, wiring)" in reason(run(project))
    done = run_untested(project, "renames a constant only", "api/src/app.py")
    assert done.returncode == 0, done.stderr
    assert done.stdout == "noted: the principles-reviewer checks the reason\n"
    assert untested.notes(project.root) == {"api/src/app.py": "renames a constant only"}
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout
    assert (
        "## Source changes Claude says need no test (check each reason)\n\n"
        "- api/src/app.py: renames a constant only" in review.brief(project.root)
    )
    project.write("api/src/app.py", "x = 2\n")
    assert "api: source changed (api/src/app.py)" in reason(run(project))


@pytest.mark.parametrize(
    ("args", "says"),
    [
        (["trivial", "api/src/app.py"], "give the reason in a few words"),
        (["renames it only", "/elsewhere/app.py"], "isn't in this project"),
    ],
)
def test_an_untested_note_needs_a_reason_and_a_project_file(
    project: Project, args: list[str], says: str
) -> None:
    commit_all(project)
    done = run_untested(project, *args)
    assert done.returncode == 1
    assert says in done.stderr


def test_tests_matched_per_component(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    project.write("web/tests/a.ts", "x\n")
    text = reason(run(project))
    assert "api: source changed" in text and "web: source changed" not in text


def test_source_and_tests_pass_and_reset_counter(project: Project) -> None:
    commit_all(project)
    project.write(".claude/alpha/state/stop-blocks", '{"count": 2}')
    project.write("api/src/app.py", "x = 1\n")
    project.write("api/tests/test_app.py", "x = 1\n")
    project.set_commands("api", typecheck=marker_cmd("t.marker"))
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    assert (project.root / "api" / "t.marker").exists()
    assert counter(project) == 0


def test_lockfile_without_dependency_log_blocks(project: Project) -> None:
    commit_all(project)
    project.write("api/pyproject.toml", "[project]\ndependencies = ['httpx']\n")
    project.write("api/uv.lock", "version = 1\n")
    text = reason(run(project))
    assert (
        "Dependencies added (api/uv.lock) without an entry in "
        "docs/alpha/dependencies.md." in text
    )
    project.write("docs/alpha/dependencies.md", "- httpx\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    assert counter(project) == 0


def test_R6_2_the_dependency_log_path_comes_from_the_principles(
    project: Project,
) -> None:
    data = project.principles()
    data["dependency_log"] = "docs/deps.md"
    project.write_principles(data)
    commit_all(project)
    project.write("api/uv.lock", "version = 1\n")
    assert "without an entry in docs/deps.md." in reason(run(project))
    project.write("docs/alpha/dependencies.md", "- httpx\n")
    assert "without an entry in docs/deps.md." in reason(run(project))
    project.write("docs/deps.md", "- httpx\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""


UV_LOCK = """version = 1

[[package]]
name = "api"
version = "{own}"
source = {{ editable = "." }}
dependencies = [{deps}]

[package.dev-dependencies]
dev = [{dev}]

[[package]]
name = "httpx"
version = "{httpx}"
source = {{ registry = "https://pypi.org/simple" }}
{extra}"""

IDNA = """
[[package]]
name = "idna"
version = "3.10"
source = { registry = "https://pypi.org/simple" }
"""


def uv_lock(
    own: str = "0.1.0",
    httpx: str = "0.27.0",
    deps: str = "",
    dev: str = "",
    extra: str = "",
) -> str:
    return UV_LOCK.format(own=own, httpx=httpx, deps=deps, dev=dev, extra=extra)


def test_own_version_bump_in_a_lockfile_needs_no_dependency_entry(
    project: Project,
) -> None:
    project.write("api/uv.lock", uv_lock())
    commit_all(project)
    project.write("api/uv.lock", uv_lock(own="0.2.0"))
    assert "without an entry in" not in run(project).stdout


@pytest.mark.parametrize(
    "changed",
    [
        {"deps": '{ name = "httpx" }'},  # a direct dependency, already pinned
        {"dev": '{ name = "httpx" }'},  # a dev dependency
    ],
)
def test_a_new_direct_dependency_needs_an_entry(
    project: Project, changed: dict[str, str]
) -> None:
    project.write("api/uv.lock", uv_lock())
    commit_all(project)
    project.write("api/uv.lock", uv_lock(own="0.2.0", **changed))
    assert "Dependencies added (api/uv.lock)" in reason(run(project))


@pytest.mark.parametrize(
    "changed",
    [
        {"httpx": "0.28.0"},  # a pin moves, as a Dependabot update does
        {"extra": IDNA},  # an upgrade pulls in a transitive package
    ],
)
def test_upgrades_need_no_dependency_entry(
    project: Project, changed: dict[str, str]
) -> None:
    project.write("api/uv.lock", uv_lock(deps='{ name = "httpx" }'))
    commit_all(project)
    project.write("api/uv.lock", uv_lock(deps='{ name = "httpx" }', **changed))
    assert "without an entry in" not in run(project).stdout


def test_a_removed_dependency_needs_no_entry(project: Project) -> None:
    project.write("api/uv.lock", uv_lock(deps='{ name = "httpx" }'))
    commit_all(project)
    project.write("api/uv.lock", uv_lock())
    assert "without an entry in" not in run(project).stdout


def test_a_dependency_logged_before_the_last_clean_stop_is_not_asked_for_again(
    project: Project,
) -> None:
    project.write("api/uv.lock", uv_lock())
    commit_all(project)
    start = project.git("rev-parse", "HEAD").stdout.strip()
    project.write(".claude/alpha/state/session-start", start + "\n")
    with_httpx = '{ name = "httpx" }'
    project.write("api/uv.lock", uv_lock(deps=with_httpx))
    project.write("docs/alpha/dependencies.md", "- httpx\n")
    commit_all(project)
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    project.write("api/uv.lock", uv_lock(own="0.2.0", deps=with_httpx))
    assert "without an entry in" not in run(project).stdout
    with_idna = uv_lock(deps=with_httpx, dev='{ name = "idna" }', extra=IDNA)
    project.write("api/uv.lock", with_idna)
    assert "Dependencies added (api/uv.lock)" in reason(run(project))


def test_own_version_bump_in_cargo_lock_needs_no_dependency_entry(
    project: Project,
) -> None:
    lock = 'version = 4\n\n[[package]]\nname = "api"\nversion = "{}"\n'
    project.write("api/Cargo.lock", lock.format("0.1.0"))
    data = project.principles()
    next(c for c in data["components"] if c["name"] == "api")["lockfiles"] = [
        "api/Cargo.lock"
    ]
    project.write_principles(data)
    commit_all(project)
    project.write("api/Cargo.lock", lock.format("0.2.0"))
    assert "without an entry in" not in run(project).stdout


CARGO_LOCK = """version = 4

[[package]]
name = "api"
version = "0.1.0"
dependencies = [{deps}]

[[package]]
name = "serde"
version = "{serde}"
source = "registry+https://github.com/rust-lang/crates.io-index"
"""


def test_cargo_lock_needs_an_entry_only_for_a_new_direct_dependency(
    project: Project,
) -> None:
    data = project.principles()
    next(c for c in data["components"] if c["name"] == "api")["lockfiles"] = [
        "api/Cargo.lock"
    ]
    project.write_principles(data)
    project.write("api/Cargo.lock", CARGO_LOCK.format(deps="", serde="1.0.0"))
    commit_all(project)
    project.write("api/Cargo.lock", CARGO_LOCK.format(deps="", serde="1.0.1"))
    assert "without an entry in" not in run(project).stdout
    project.write("api/Cargo.lock", CARGO_LOCK.format(deps='"serde"', serde="1.0.1"))
    assert "Dependencies added (api/Cargo.lock)" in reason(run(project))


def test_manifest_config_change_needs_no_dependency_entry(project: Project) -> None:
    commit_all(project)
    project.write(
        "api/pyproject.toml", "[tool.pytest.ini_options]\npythonpath = ['.']\n"
    )
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


def guide_mapped(project: Project) -> None:
    data = project.principles()
    data["docs_map"] = {"api/src/**/*.py": ["docs/guide/**"]}
    project.write_principles(data)
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")


def test_docs_drift_satisfied_by_any_file_under_a_doc_glob(project: Project) -> None:
    guide_mapped(project)
    project.write("docs/guide/api/upload.md", "doc\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""


def test_docs_drift_glob_still_flags_unrelated_doc_changes(project: Project) -> None:
    guide_mapped(project)
    project.write("docs/other.md", "doc\n")
    assert "api/src/a.py changed but docs/guide/** did not." in reason(run(project))


def map_docs(project: Project, docs_map: dict[str, list[str]]) -> None:
    data = project.principles()
    data["docs_map"] = docs_map
    project.write_principles(data)
    commit_all(project)


def test_test_only_change_under_a_mapped_path_needs_no_docs(project: Project) -> None:
    map_docs(project, {"api/**/routes/**": ["docs/guide/**"]})
    project.write("api/tests/routes/test_users.py", "x = 1\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


def test_a_doc_under_a_mapped_path_is_not_code(project: Project) -> None:
    map_docs(
        project,
        {"**/api/**": ["docs/architecture.md"], "web/**": ["docs/guide/**"]},
    )
    project.write("docs/guide/api/upload.md", "doc\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


def test_a_docs_note_holds_until_the_file_changes(project: Project) -> None:
    """A mapped change that alters no documented behavior (an internal
    refactor) needs no doc change: Claude says why once, instead of being
    blocked at every Stop."""
    guide_mapped(project)
    text = reason(run(project))
    assert "api/src/a.py changed but docs/guide/** did not." in text
    assert "untested.py --docs" in text
    done = run_untested(project, "--docs", "moves dispatch only", "api/src/a.py")
    assert done.returncode == 0, done.stderr
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout
    assert (
        "## Changes Claude says need no doc update (check each reason)\n\n"
        "- api/src/a.py: moves dispatch only" in review.brief(project.root)
    )
    project.write("api/src/a.py", "y\n")
    assert "api/src/a.py changed but docs/guide/** did not." in reason(run(project))


def test_a_test_note_is_not_a_docs_note(project: Project) -> None:
    guide_mapped(project)
    run_untested(project, "renames a constant only", "api/src/a.py")
    assert "api/src/a.py changed but docs/guide/** did not." in reason(run(project))
    assert untested.notes(project.root, "docs") == {}


def test_docs_drift_with_hand_set_docs_map(project: Project) -> None:
    data = project.principles()
    data["docs_map"] = {"api/src/**/*.py": ["docs/api.md"]}
    project.write_principles(data)
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    text = reason(run(project))
    assert "api/src/a.py changed but docs/api.md did not." in text
    assert "Principle docs-with-code" in text
    project.write("docs/api.md", "doc\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    assert counter(project) == 0


def test_failing_check_blocks_with_tail(project: Project) -> None:
    project.set_commands(
        "api",
        typecheck="python3 -c \"print('\\n'.join(f'L{i}' for i in range(100))); "
        'raise SystemExit(1)"',
    )
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    text = reason(run(project))
    assert "api: typecheck failed (python3 -c" in text
    assert "L99" in text and "L40" in text and "L39\n" not in text


def test_R13_1_stop_runs_types_structure_and_fast_checks(project: Project) -> None:
    enable_repo_checks(project, "typos")
    project.set_commands(
        "api", typecheck=FAIL, structure=FAIL, test=marker_cmd("t.marker")
    )
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    text = reason(run_with(project, fake_mise(project)))
    assert "api: typecheck failed" in text and "api: structure failed" in text
    assert calls(project) == ["run check:typos"]
    assert not (project.root / "api" / "t.marker").exists()  # no test suite


def test_missing_tool_gives_setup_hint(project: Project) -> None:
    project.set_commands(
        "api", typecheck="definitely-not-a-tool-xyz", setup="make setup"
    )
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    text = reason(run(project))
    assert "definitely-not-a-tool-xyz is not installed for component api" in text
    assert "make setup" in text


def test_only_affected_components_run(project: Project) -> None:
    project.set_commands("web", typecheck=marker_cmd("w.marker"))
    project.set_commands("api", typecheck=marker_cmd("a.marker"))
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    assert (project.root / "api" / "a.marker").exists()
    assert not (project.root / "web" / "w.marker").exists()


def test_three_blocks_then_gives_up(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    for n in (1, 2, 3):
        reason(run(project))
        assert counter(project) == n
    proc = run(project)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["systemMessage"] == proc.stderr.rstrip("\n")
    assert proc.stderr.startswith(
        "alpha: checks still failing after 3 attempts; stopping so the user can decide:"
    )
    assert "tests-first-class" in proc.stderr
    assert counter(project) == 0


def test_clean_tree_runs_nothing_and_resets(project: Project) -> None:
    project.set_commands("api", typecheck=marker_cmd("t.marker"))
    commit_all(project)
    project.write(".claude/alpha/state/stop-blocks", '{"count": 2}')
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "" and proc.stderr == ""
    assert not (project.root / "api" / "t.marker").exists()
    assert counter(project) == 0


def test_timeout_raises_timed_out(project: Project, monkeypatch: Any) -> None:
    monkeypatch.setattr(stop_checks, "TIMEOUT", 1)
    out = stop_checks.run_step("sleep 5", project.root)
    assert out[0] == "timeout"


def test_added_content_cannot_spoof_diff_headers(project: Project) -> None:
    project.write("a.txt", "x\n")
    commit_all(project)
    project.write("a.txt", f"x\n++ b/zzz\n++ foo\nkey = {AWS_KEY}\n")
    text = reason(run(project))
    assert "a.txt:4" in text and "zzz" not in text


def test_sk_pattern_ignores_kebab_words(project: Project) -> None:
    commit_all(project)
    project.write("a.md", "risk-based-authentication-flow and task-12-brief-name-x\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    project.write("b.txt", "k = sk-proj-" + "a" * 24 + "\n")
    assert "b.txt:1" in reason(run(project))


def test_commit_after_baseline_still_checked(project: Project) -> None:
    project.write("README.md", "hi\n")
    commit_all(project)
    base = project.git("rev-parse", "HEAD").stdout.strip()
    project.write("api/src/app.py", "x = 1\n")
    commit_all(project)
    project.write(".claude/alpha/state/session-base", base)
    text = reason(run(project))
    assert "api: source changed (api/src/app.py)" in text


def test_clean_run_updates_baseline(project: Project) -> None:
    commit_all(project)
    head = project.git("rev-parse", "HEAD").stdout.strip()
    proc = run(project)
    assert proc.returncode == 0
    path = project.root / ".claude" / "alpha" / "state" / "session-base"
    assert path.read_text().strip() == head


def test_non_ancestor_baseline_falls_back_to_head(project: Project) -> None:
    commit_all(project)
    project.write(".claude/alpha/state/session-base", "0" * 40)
    project.write("api/src/app.py", "x = 1\n")
    assert "tests-first-class" in reason(run(project))


def test_readme_only_change_runs_nothing(project: Project) -> None:
    project.set_commands("api", typecheck=marker_cmd("t.marker"))
    project.write("api/README.md", "a\n")
    commit_all(project)
    project.write("api/README.md", "b\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    assert not (project.root / "api" / "t.marker").exists()


def test_budget_exhausted_skips_steps(project: Project, monkeypatch: Any) -> None:
    project.set_commands("api", typecheck=STUB, structure="", test=STUB)
    data = project.principles()
    monkeypatch.setattr(stop_checks, "BUDGET", 0)
    problems = stop_checks.command_problems(
        data["components"][0], data, project.root, 0.0, EVERY_STEP
    )
    assert len(problems) == 2
    assert (
        "api: typecheck skipped \u2014 alpha's 0s check budget ran out."
        in (problems[0])
    )
    assert "Run it by hand: " + STUB in problems[0]


def test_dropped_tests_first_class_does_not_block(project: Project) -> None:
    project.drop_principle("tests-first-class")
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""


def test_tests_first_class_dropped_for_one_component(project: Project) -> None:
    project.drop_principle("tests-first-class", component="api")
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    project.write("web/src/app.ts", "x\n")
    text = reason(run(project))
    assert "web: source changed" in text
    assert "api: source changed" not in text


def test_dropped_dependency_reasons_does_not_block(project: Project) -> None:
    project.drop_principle("dependency-reasons", component="api")
    commit_all(project)
    project.write("api/uv.lock", "version = 1\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""


def test_dropped_no_secrets_does_not_block(project: Project) -> None:
    project.drop_principle("no-secrets")
    commit_all(project)
    project.write("notes.txt", f"key = {AWS_KEY}\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""


def test_dropped_docs_with_code_does_not_block(project: Project) -> None:
    data = project.principles()
    data["docs_map"] = {"api/src/**/*.py": ["docs/api.md"]}
    project.write_principles(data)
    project.drop_principle("docs-with-code")
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""


def test_dropped_strict_types_and_dead_code_skip_commands(project: Project) -> None:
    project.set_commands("api", typecheck=FAIL, structure=FAIL)
    project.drop_principle("strict-types", component="api")
    project.drop_principle("no-dead-code", component="api")
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""


def test_flat_layout_source_is_checked(project: Project) -> None:
    project.set_commands("api", typecheck=FAIL)
    commit_all(project)
    project.write("api/main.py", "x: int = 'no'\n")
    text = reason(run(project))
    assert "api: source changed (api/main.py) but no tests changed." in text
    assert "api: typecheck failed" in text


def test_vendored_files_are_not_source(project: Project) -> None:
    project.set_commands("api", typecheck=FAIL)
    commit_all(project)
    project.write("api/.venv/lib/site.py", "x = 1\n")
    project.write("api/build/lib/main.py", "x = 1\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""


def give_up(project: Project) -> None:
    for _ in range(3):
        reason(run(project))
    proc = run(project)
    assert (
        "checks still failing after 3 attempts"
        in json.loads(proc.stdout)["systemMessage"]
    )


def test_same_findings_after_give_up_only_flag(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    give_up(project)
    for _ in range(2):
        proc = run(project)
        assert proc.returncode == 0
        out = json.loads(proc.stdout)
        assert "decision" not in out
        assert out["systemMessage"].startswith("alpha: still open")
        assert "tests-first-class" in out["systemMessage"]
        assert counter(project) == 0


def test_changed_findings_after_give_up_block_again(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    give_up(project)
    project.write("api/src/other.py", "y = 2\n")
    text = reason(run(project))
    assert "other.py" in text
    assert counter(project) == 1


def test_secrets_never_give_up(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    project.write("notes.txt", f"key = {AWS_KEY}\n")
    for _ in range(6):
        text = reason(run(project))
        assert "notes.txt:1" in text
        assert "tests-first-class" in text
    assert not (project.root / ".claude/alpha/state/stop-accepted").exists()


def test_given_up_findings_block_again_with_a_secret(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    give_up(project)
    project.write("notes.txt", f"key = {AWS_KEY}\n")
    for _ in range(4):
        assert "notes.txt:1" in reason(run(project))
    (project.root / "notes.txt").unlink()
    out = json.loads(run(project).stdout)
    assert out["systemMessage"].startswith("alpha: still open")


def test_fixed_findings_clear_the_accepted_set(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    give_up(project)
    project.write("api/tests/test_app.py", "x = 1\n")
    assert run(project).stdout == ""
    (project.root / "api/tests/test_app.py").unlink()
    reason(run(project))


def test_unchanged_tree_reuses_command_results(project: Project) -> None:
    fail_and_mark = (
        "python3 -c \"open('../t.marker', 'a').write('x'); raise SystemExit(1)\""
    )
    project.set_commands("api", typecheck=fail_and_mark)
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    first = reason(run(project))
    second = reason(run(project))
    assert first == second and "api: typecheck failed" in first
    marker = project.root / "t.marker"
    assert marker.read_text() == "x"
    project.write("api/src/a.py", "y\n")
    reason(run(project))
    assert marker.read_text() == "xx"


def test_changed_command_is_rerun(project: Project) -> None:
    project.set_commands("api", typecheck=marker_cmd("../t.marker"))
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    assert run(project).stdout == ""
    assert run(project).stdout == ""
    marker = project.root / "t.marker"
    assert marker.read_text() == "x"
    project.set_commands("api", typecheck=FAIL)
    assert "api: typecheck failed" in reason(run(project))


def test_missing_tool_is_not_cached(project: Project) -> None:
    project.set_commands("api", typecheck="definitely-not-a-tool-xyz")
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    assert "is not installed" in reason(run(project))
    bin_dir = project.root / "bin"
    tool = project.write("bin/definitely-not-a-tool-xyz", "#!/bin/sh\nexit 0\n")
    tool.chmod(0o755)
    proc = project.run_hook(
        "stop_checks.py", PAYLOAD, env={"PATH": f"{bin_dir}:{os.environ['PATH']}"}
    )
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


def subagent_stop(project: Project, agent: str) -> subprocess.CompletedProcess[str]:
    return project.run_hook(
        "stop_checks.py",
        {
            "hook_event_name": "SubagentStop",
            "stop_hook_active": False,
            "agent_id": agent,
            "agent_type": "general-purpose",
        },
    )


def edited_by(project: Project, agent: str, *rels: str) -> None:
    project.write(
        f".claude/alpha/state/agent-{agent}.json", json.dumps({"files": list(rels)})
    )


def test_subagent_without_edits_stops_freely(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    proc = subagent_stop(project, "r1")
    assert proc.returncode == 0 and proc.stdout == ""


def test_subagent_is_blocked_on_its_own_untested_source(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    project.write("api/src/x.py", "y = 2\n")
    edited_by(project, "a1", "api/src/x.py")
    text = reason(subagent_stop(project, "a1"))
    assert "api/src/x.py" in text
    assert text.endswith(
        "You edited api/src/x.py. Fix the problems in those files only; report "
        "the rest to the main session."
    )


def test_subagent_secret_blocks_every_time(project: Project) -> None:
    commit_all(project)
    project.write("notes.txt", f"key = {AWS_KEY}\n")
    edited_by(project, "a1", "notes.txt")
    for _ in range(5):
        assert "notes.txt:1" in reason(subagent_stop(project, "a1"))


def test_clean_subagent_stop_clears_its_state(project: Project) -> None:
    commit_all(project)
    project.write("api/src/x.py", "y = 2\n")
    project.write("api/tests/test_x.py", "y = 2\n")
    edited_by(project, "a1", "api/src/x.py", "api/tests/test_x.py")
    proc = subagent_stop(project, "a1")
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout
    assert not (project.root / ".claude/alpha/state/agent-a1.json").exists()


def test_subagent_blocks_count_separately_from_the_main_session(
    project: Project,
) -> None:
    commit_all(project)
    project.write("api/src/x.py", "y = 2\n")
    edited_by(project, "a1", "api/src/x.py")
    for _ in range(3):
        reason(subagent_stop(project, "a1"))
    assert counter(project) == 0
    proc = subagent_stop(project, "a1")
    out = json.loads(proc.stdout)
    assert "decision" not in out
    assert "main session can decide" not in out["systemMessage"]
    assert "the main session's Stop still checks them" in out["systemMessage"]


def test_subagent_implementing_tests_the_session_wrote_is_not_blocked(
    project: Project,
) -> None:
    commit_all(project)
    project.write("api/tests/test_x.py", "def test_x() -> None: ...\n")
    project.write("api/src/x.py", "y = 2\n")
    edited_by(project, "a1", "api/src/x.py")
    proc = subagent_stop(project, "a1")
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


def test_subagent_stop_leaves_component_commands_to_the_main_stop(
    project: Project,
) -> None:
    project.set_commands("api", typecheck=FAIL, structure=FAIL)
    commit_all(project)
    project.write("api/src/x.py", "y = 2\n")
    project.write("api/tests/test_x.py", "y = 2\n")
    edited_by(project, "a1", "api/src/x.py", "api/tests/test_x.py")
    proc = subagent_stop(project, "a1")
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


MIGRATION = "api/migrations/versions/0001_init.sql"


def committed_migration(project: Project) -> str:
    project.write(MIGRATION, "create table t (id int);\n")
    commit_all(project)
    base = project.git("rev-parse", "HEAD").stdout.strip()
    project.write(".claude/alpha/state/session-base", base)
    return base


def test_editing_a_committed_migration_blocks(project: Project) -> None:
    base = committed_migration(project)
    project.write(MIGRATION, "create table t (id bigint);\n")
    text = reason(run(project))
    assert (
        f"{MIGRATION} existed before this session and was changed. Migrations are "
        f"append-only: put it back (git checkout {base} -- {MIGRATION}) and add a "
        "new migration instead. Principle safe-migrations."
    ) in text


def test_checkout_advice_quotes_a_path_with_spaces(project: Project) -> None:
    spaced = "api/migrations/versions/0002 add index.sql"
    project.write(spaced, "create index i on t (id);\n")
    base = committed_migration(project)
    project.write(spaced, "drop index i;\n")
    assert f"git checkout {base} -- '{spaced}'" in reason(run(project))


def test_deleting_a_committed_migration_blocks(project: Project) -> None:
    committed_migration(project)
    (project.root / MIGRATION).unlink()
    assert f"{MIGRATION} existed before this session" in reason(run(project))


def test_editing_a_committed_migration_blocks_without_a_recorded_base(
    project: Project,
) -> None:
    committed_migration(project)
    (project.root / ".claude/alpha/state/session-base").unlink()
    project.write(MIGRATION, "drop table t;\n")
    assert f"{MIGRATION} existed before this session" in reason(run(project))


def test_a_new_migration_passes(project: Project) -> None:
    committed_migration(project)
    project.write("api/migrations/versions/0002_more.sql", "alter table t add c int;\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


def test_a_migration_created_and_edited_this_session_passes(project: Project) -> None:
    committed_migration(project)
    project.write("api/migrations/versions/0002_more.sql", "alter table t add c int;\n")
    commit_all(project)
    project.write("api/migrations/versions/0002_more.sql", "alter table t add d int;\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


def test_dropped_safe_migrations_does_not_block(project: Project) -> None:
    project.drop_principle("safe-migrations")
    committed_migration(project)
    project.write(MIGRATION, "create table t (id bigint);\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


def test_files_outside_the_migration_paths_are_not_migrations(
    project: Project,
) -> None:
    project.write("api/migrations/env.py", "target_metadata = None\n")
    committed_migration(project)
    project.write("api/migrations/env.py", "target_metadata = Base.metadata\n")
    project.write("api/tests/test_env.py", "def test_env() -> None: ...\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


def test_without_commits_migrations_are_not_checked(project: Project) -> None:
    project.write(MIGRATION, "create table t (id int);\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout


def test_a_subagent_editing_a_committed_migration_is_blocked(project: Project) -> None:
    committed_migration(project)
    project.write(MIGRATION, "create table t (id bigint);\n")
    edited_by(project, "a1", MIGRATION)
    assert f"{MIGRATION} existed before this session" in reason(
        subagent_stop(project, "a1")
    )


def test_renaming_a_committed_migration_blocks(project: Project) -> None:
    committed_migration(project)
    project.git("mv", MIGRATION, "api/migrations/versions/0001_init_v2.sql")
    assert f"{MIGRATION} existed before this session" in reason(run(project))


def test_renaming_and_editing_a_committed_migration_blocks(project: Project) -> None:
    lines = "".join(f"create table t{i} (id int);\n" for i in range(30))
    project.write(MIGRATION, lines)
    commit_all(project)
    base = project.git("rev-parse", "HEAD").stdout.strip()
    project.write(".claude/alpha/state/session-base", base)
    renamed = "api/migrations/versions/0001_init_v2.sql"
    project.git("mv", MIGRATION, renamed)
    project.write(renamed, lines.replace("t0 (id int)", "t0 (id bigint)"))
    commit_all(project)
    assert f"{MIGRATION} existed before this session" in reason(run(project))


def test_a_migration_committed_in_an_earlier_turn_can_still_be_edited(
    project: Project,
) -> None:
    start = committed_migration(project)
    project.write(".claude/alpha/state/session-start", start)
    project.write("api/migrations/versions/0002_more.sql", "alter table t add c int;\n")
    commit_all(project)
    head = project.git("rev-parse", "HEAD").stdout.strip()
    project.write(".claude/alpha/state/session-base", head)
    project.write("api/migrations/versions/0002_more.sql", "alter table t add d int;\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout
    project.write(MIGRATION, "drop table t;\n")
    assert f"git checkout {start} -- {MIGRATION}" in reason(run(project))


def test_a_new_session_records_where_it_started(project: Project) -> None:
    commit_all(project)
    head = project.git("rev-parse", "HEAD").stdout.strip()
    project.run_hook(
        "session_start.py", {"hook_event_name": "SessionStart", "source": "startup"}
    )
    start = project.root / ".claude/alpha/state/session-start"
    assert start.read_text().strip() == head
    project.write("x.txt", "x\n")
    commit_all(project)
    project.run_hook(
        "session_start.py", {"hook_event_name": "SessionStart", "source": "resume"}
    )
    assert start.read_text().strip() == head


def enable_repo_checks(project: Project, *ids: str) -> None:
    data = project.principles()
    for check in data["repo_checks"]:
        check["stop"] = check["id"] in ids
    project.write_principles(data)


def fake_mise(project: Project, code: int = 0) -> dict[str, str | None]:
    """A `mise` on PATH that logs each task it is asked to run to calls.log."""
    log = project.root.parent / f"{project.root.name}-calls.log"
    script = project.write(
        "fake-bin/mise", f'#!/bin/sh\necho "$@" >> "{log}"\nexit {code}\n'
    )
    script.chmod(0o755)
    return {"PATH": f"{script.parent}:{os.environ['PATH']}"}


def calls(project: Project) -> list[str]:
    log = project.root.parent / f"{project.root.name}-calls.log"
    return log.read_text().splitlines() if log.exists() else []


def run_with(project: Project, env: dict[str, str | None]) -> Any:
    return project.run_hook("stop_checks.py", PAYLOAD, env=env)


def test_stop_runs_matching_repo_check(project: Project) -> None:
    enable_repo_checks(project, "typos", "actions")
    commit_all(project)
    project.write("README.md", "hello\n")
    proc = run_with(project, fake_mise(project))
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout
    assert calls(project) == ["run check:typos"]


def test_stop_repo_check_failure_blocks(project: Project) -> None:
    enable_repo_checks(project, "typos")
    commit_all(project)
    project.write("README.md", "hello\n")
    proc = run_with(project, fake_mise(project, code=2))
    assert "repo check typos failed (mise run check:typos)" in reason(proc)


def test_stop_repo_check_missing_mise(project: Project) -> None:
    enable_repo_checks(project, "typos", "markdown")
    commit_all(project)
    project.write("README.md", "hello\n")
    empty = project.root.parent / "empty-bin"
    empty.mkdir()
    git = shutil.which("git")
    assert git is not None
    (empty / "git").symlink_to(git)  # git stays; mise doesn't
    env: dict[str, str | None] = {"PATH": str(empty)}
    for _ in range(3):
        proc = project.run_hook("stop_checks.py", PAYLOAD, env=env)
        text = reason(proc)
        assert text.count("mise install") == 1
        assert text.count("\n") == 1  # header plus exactly one problem
    final = project.run_hook("stop_checks.py", PAYLOAD, env=env)
    assert final.returncode == 0
    assert final.stderr.startswith("alpha: checks still failing after 3 attempts")


def test_stop_repo_check_cached(project: Project) -> None:
    enable_repo_checks(project, "typos")
    commit_all(project)
    project.write("README.md", "hello\n")
    env = fake_mise(project)
    assert run_with(project, env).stdout == ""
    assert run_with(project, env).stdout == ""
    assert calls(project) == ["run check:typos"]
    project.write("README.md", "changed\n")
    assert run_with(project, env).stdout == ""
    assert len(calls(project)) == 2


def test_subagent_stop_runs_repo_check_on_its_files(project: Project) -> None:
    enable_repo_checks(project, "typos")
    commit_all(project)
    project.write("README.md", "hello\n")
    edited_by(project, "ag1", "README.md")
    env = fake_mise(project, code=2)
    proc = project.run_hook(
        "stop_checks.py",
        {
            "hook_event_name": "SubagentStop",
            "stop_hook_active": False,
            "agent_id": "ag1",
            "agent_type": "general-purpose",
        },
        env=env,
    )
    assert "repo check typos failed" in reason(proc)


def test_finished_checks_are_cached_when_a_later_one_is_missing(
    project: Project,
) -> None:
    enable_repo_checks(project, "typos", "markdown")
    commit_all(project)
    project.write("README.md", "hello\n")
    log = project.root.parent / f"{project.root.name}-calls.log"
    script = project.write(
        "fake-bin/mise",
        f'#!/bin/sh\necho "$@" >> "{log}"\n'
        '[ "$2" = check:markdown ] && exit 127\nexit 0\n',
    )
    script.chmod(0o755)
    env: dict[str, str | None] = {"PATH": f"{script.parent}:{os.environ['PATH']}"}
    assert "mise install" in reason(run_with(project, env))
    assert "mise install" in reason(run_with(project, env))
    assert calls(project) == [
        "run check:typos",
        "run check:markdown",
        "run check:markdown",
    ]


def test_cached_failed_repo_check_is_reported_without_rerunning(
    project: Project,
) -> None:
    enable_repo_checks(project, "typos")
    commit_all(project)
    project.write("README.md", "hello\n")
    env = fake_mise(project, code=2)
    first = reason(run_with(project, env))
    second = reason(run_with(project, env))
    assert first == second and "repo check typos failed" in first
    assert len(calls(project)) == 1


def test_component_and_repo_check_failures_both_block(project: Project) -> None:
    project.set_commands("api", typecheck=FAIL)
    enable_repo_checks(project, "typos")
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    text = reason(run_with(project, fake_mise(project, code=2)))
    assert "api: typecheck failed" in text
    assert "repo check typos failed" in text


def test_deleted_matched_file_does_not_crash(project: Project) -> None:
    enable_repo_checks(project, "typos", "markdown")
    project.write("README.md", "hello\n")
    commit_all(project)
    (project.root / "README.md").unlink()
    proc = run_with(project, fake_mise(project))
    assert proc.returncode == 0 and proc.stdout == "", proc.stderr


def test_slot_wait_past_deadline_is_a_problem_and_not_cached(
    project: Project, monkeypatch: Any, tmp_path: Any
) -> None:
    @contextlib.contextmanager
    def no_slot(deadline: float) -> Any:
        yield False

    monkeypatch.setattr(_common, "heavy_slot", no_slot)
    project.set_commands("api", typecheck=STUB, structure="", test="")
    data = project.principles()
    problems = stop_checks.command_problems(
        data["components"][0], data, project.root, time.monotonic() + 100, EVERY_STEP
    )
    assert len(problems) == 1
    assert (
        f"waited for other agents' checks until alpha's {stop_checks.BUDGET}s "
        f"budget ran out; run {STUB} by hand"
    ) in problems[0]
    assert not (project.root / "api" / "t.marker").exists()
    cache = project.root / ".claude" / "alpha" / "state" / "stop-cache.json"
    assert not cache.exists() or "typecheck" not in cache.read_text()


def test_heavy_step_uses_slots_under_the_test_home(
    project: Project, isolated_home: Any
) -> None:
    project.set_commands("api", typecheck=STUB, structure="", test="")
    (project.root / "api" / "app").mkdir(parents=True, exist_ok=True)
    (project.root / "api" / "app" / "x.py").write_text("x = 1\n")
    project.run_hook("stop_checks.py", {"cwd": str(project.root)})
    assert (isolated_home / ".cache" / "alpha" / "slots" / "0.lock").is_file()


def marks(project: Project, rel: str) -> int:
    path = project.root / rel
    return path.stat().st_size if path.exists() else 0


def test_tests_command_runs_the_changed_components_once_per_tree(
    project: Project,
) -> None:
    project.set_commands("api", test=marker_cmd("../t.marker"))
    project.set_commands("web", test=marker_cmd("../w.marker"))
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    proc = project.run_tests()
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "tests passed: api\n"
    assert marks(project, "t.marker") == 1
    assert marks(project, "w.marker") == 0
    assert project.run_tests().returncode == 0
    assert marks(project, "t.marker") == 1  # the same files: not run again
    project.write("api/src/a.py", "y\n")
    assert project.run_tests().returncode == 0
    assert marks(project, "t.marker") == 2


def test_tests_command_fails_with_the_suites_output(project: Project) -> None:
    project.set_commands("api", test=FAIL)
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    proc = project.run_tests()
    assert proc.returncode == 1
    assert "api: test failed (python3 -c" in proc.stderr
    assert "boom" in proc.stderr


def test_tests_command_with_nothing_changed_says_so(project: Project) -> None:
    commit_all(project)
    proc = project.run_tests()
    assert proc.returncode == 0
    assert proc.stdout == "tests passed: no component changed\n"


def test_a_failed_tests_run_is_tried_again_on_the_same_files(project: Project) -> None:
    flaky = (
        'python3 -c "import os, sys; '
        "sys.exit(0 if os.path.exists('../service-up') else 1)\""
    )
    project.set_commands("api", test=flaky)
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    assert project.run_tests().returncode == 1
    project.write("service-up")  # outside every component: the files are the same
    assert project.run_tests().returncode == 0


def test_tests_command_is_not_held_to_the_stop_limits(
    project: Project, monkeypatch: Any
) -> None:
    data = project.principles()
    limits: list[float] = []

    def record(command: str, cwd: Any, limit: float) -> tuple[int, str]:
        limits.append(limit)
        return 0, ""

    monkeypatch.setattr(_common, "run_command", record)
    deadline = time.monotonic() + stop_checks.TESTS_LIMIT
    comp = data["components"][0]
    assert (
        stop_checks.command_problems(
            comp, data, project.root, deadline, stop_checks.TESTS
        )
        == []
    )
    assert limits and limits[0] > stop_checks.TIMEOUT


def share_workspace(project: Project) -> None:
    """Both components as members of one workspace: its manifest and lockfile
    are at the root, in neither's folder."""
    data = project.principles()
    for comp in data["components"]:
        comp["manifests"].append("Workspace.toml")
        comp["lockfiles"] = ["shared.lock"]
    project.write_principles(data)


def test_workspace_manifest_change_runs_every_member_s_checks(project: Project) -> None:
    share_workspace(project)
    project.set_commands("api", typecheck=marker_cmd("t.marker"))
    project.set_commands("web", typecheck=marker_cmd("w.marker"))
    project.write("api/tests/test_x.py")
    project.write("web/tests/x.test.ts")
    commit_all(project)
    project.write("Workspace.toml", "[workspace]\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    assert (project.root / "api" / "t.marker").exists()
    assert (project.root / "web" / "w.marker").exists()


def test_workspace_lockfile_needs_one_dependency_entry(project: Project) -> None:
    share_workspace(project)
    commit_all(project)
    project.write("shared.lock", "version = 1\n")
    text = reason(run(project))
    problem = "Dependencies added (shared.lock) without an entry in"
    assert text.count(problem) == 1  # once, not once per member
    project.write("docs/alpha/dependencies.md", "- httpx\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""


def test_R9_1_stop_never_asks_for_a_review(project: Project) -> None:
    commit_all(project)
    project.git("switch", "-q", "-c", "feature")
    for i in range(40):
        project.write(f"api/src/m{i}.py", "\n".join(f"x{n} = {n}" for n in range(50)))
        project.write(f"api/tests/test_m{i}.py", "def test_x():\n    assert True\n")
    proc = run(project)
    assert proc.returncode == 0, proc.stderr
    assert "principles-reviewer" not in proc.stdout + proc.stderr


def test_R17_1_not_code_needs_no_tests_or_docs(project: Project) -> None:
    project.set_not_code("api/examples", "docs/research/*/experiments")
    project.set_commands("api", typecheck=FAIL, structure=FAIL)
    map_docs(project, {"api/**": ["docs/guide/**"], "docs/research/**": ["x.md"]})
    project.write("api/examples/app.py", "x = 1\n")
    project.write("docs/research/r1/experiments/run.py", "x = 1\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "", proc.stdout
    project.write("api/src/app.py", "x = 1\n")
    text = reason(run(project))
    assert "api: source changed (api/src/app.py) but no tests" in text
    assert "api/src/app.py changed but docs/guide/** did not." in text
    assert "api: typecheck failed" in text
    assert "examples" not in text and "experiments" not in text


def test_R17_1_secrets_are_found_in_not_code(project: Project) -> None:
    project.set_not_code("api/examples")
    commit_all(project)
    project.write("api/examples/settings.py", f"KEY = '{AWS_KEY}'\n")
    assert "api/examples/settings.py:1" in reason(run(project))


def test_R17_1_not_code_runs_no_test_suite(project: Project) -> None:
    project.set_not_code("api/examples")
    project.set_commands("api", test=FAIL)
    commit_all(project)
    project.write("api/examples/app.py", "x\n")
    proc = project.run_tests()
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "tests passed: no component changed\n"
