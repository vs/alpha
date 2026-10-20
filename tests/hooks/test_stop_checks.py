import json
import os
import subprocess
from typing import Any

from .conftest import STUB, Project

FAIL = "python3 -c \"import sys; print('boom'); sys.exit(1)\""
PAYLOAD: dict[str, Any] = {"hook_event_name": "Stop", "stop_hook_active": False}
AWS_KEY = "AKIA" + "A" * 16


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
    project.write("a.txt", "x\npassword = 'hunter2hunter2'\n")
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
    project.set_commands("api", test=marker_cmd("t.marker"))
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    assert (project.root / "api" / "t.marker").exists()
    assert counter(project) == 0


def test_manifest_without_dependency_log_blocks(project: Project) -> None:
    commit_all(project)
    project.write("api/pyproject.toml", "[project]\n")
    text = reason(run(project))
    assert "Dependency manifest changed (api/pyproject.toml) without an entry" in text
    assert "docs/dependencies.md" in text
    project.write("docs/dependencies.md", "- httpx\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    assert counter(project) == 0


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


def test_failing_test_blocks_with_tail(project: Project) -> None:
    project.set_commands(
        "api",
        test="python3 -c \"print('\\n'.join(f'L{i}' for i in range(100))); "
        'raise SystemExit(1)"',
    )
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    text = reason(run(project))
    assert "api: test failed (python3 -c" in text
    assert "L99" in text and "L40" in text and "L39\n" not in text


def test_typecheck_runs_before_test_and_failure_blocks(project: Project) -> None:
    project.set_commands("api", typecheck=FAIL, test=marker_cmd("t.marker"))
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    text = reason(run(project))
    assert "api: typecheck failed" in text
    assert (project.root / "api" / "t.marker").exists()  # test still runs


def test_missing_tool_gives_setup_hint(project: Project) -> None:
    project.set_commands("api", test="definitely-not-a-tool-xyz", setup="make setup")
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    text = reason(run(project))
    assert "definitely-not-a-tool-xyz is not installed for component api" in text
    assert "make setup" in text


def test_only_affected_components_run(project: Project) -> None:
    project.set_commands("web", test=marker_cmd("w.marker"))
    project.set_commands("api", test=marker_cmd("a.marker"))
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
    project.set_commands("api", test=marker_cmd("t.marker"), typecheck=STUB)
    commit_all(project)
    project.write(".claude/alpha/state/stop-blocks", '{"count": 2}')
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == "" and proc.stderr == ""
    assert not (project.root / "api" / "t.marker").exists()
    assert counter(project) == 0


def test_timeout_raises_timed_out(project: Project, monkeypatch: Any) -> None:
    import stop_checks

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
    project.set_commands("api", test=marker_cmd("t.marker"))
    project.write("api/README.md", "a\n")
    commit_all(project)
    project.write("api/README.md", "b\n")
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    assert not (project.root / "api" / "t.marker").exists()


def test_budget_exhausted_skips_steps(project: Project, monkeypatch: Any) -> None:
    import stop_checks

    project.set_commands("api", typecheck=STUB, test=STUB)
    data = project.principles()
    monkeypatch.setattr(stop_checks, "BUDGET", 0)
    problems = stop_checks.command_problems(
        data["components"][0], data, project.root, 0.0
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
    project.write("api/pyproject.toml", "[project]\n")
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


def test_dropped_strict_types_and_done_skip_commands(project: Project) -> None:
    project.set_commands("api", typecheck=FAIL, test=FAIL)
    project.drop_principle("strict-types", component="api")
    project.drop_principle("definition-of-done", component="api")
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
    project.set_commands("api", typecheck=FAIL, test=FAIL)
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
    project.write("notes.txt", f"key = {AWS_KEY}\n")
    text = reason(run(project))
    assert "notes.txt:1" in text
    assert counter(project) == 1


def test_fixed_findings_clear_the_accepted_set(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    give_up(project)
    project.write("api/tests/test_app.py", "x = 1\n")
    assert run(project).stdout == ""
    (project.root / "api/tests/test_app.py").unlink()
    reason(run(project))  # the same finding as before blocks again


def test_unchanged_tree_reuses_command_results(project: Project) -> None:
    # Markers go outside the component: files it creates would change its tree.
    fail_and_mark = (
        "python3 -c \"open('../t.marker', 'a').write('x'); raise SystemExit(1)\""
    )
    project.set_commands("api", test=fail_and_mark)
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    first = reason(run(project))
    second = reason(run(project))
    assert first == second and "api: test failed" in first
    marker = project.root / "t.marker"
    assert marker.read_text() == "x"
    project.write("api/src/a.py", "y\n")
    reason(run(project))
    assert marker.read_text() == "xx"


def test_changed_command_is_rerun(project: Project) -> None:
    project.set_commands("api", test=marker_cmd("../t.marker"))
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    assert run(project).stdout == ""
    assert run(project).stdout == ""
    marker = project.root / "t.marker"
    assert marker.read_text() == "x"
    project.set_commands("api", test=FAIL)
    assert "api: test failed" in reason(run(project))


def test_missing_tool_is_not_cached(project: Project) -> None:
    project.set_commands("api", test="definitely-not-a-tool-xyz")
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
