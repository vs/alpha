import json
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
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
    assert counter(project) == 0


def test_manifest_without_dependency_log_blocks(project: Project) -> None:
    commit_all(project)
    project.write("api/pyproject.toml", "[project]\n")
    text = reason(run(project))
    assert "Dependency manifest changed (api/pyproject.toml) without an entry" in text
    assert "docs/dependencies.md" in text
    project.write("docs/dependencies.md", "- httpx\n")
    assert run(project).stdout == ""


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
    assert run(project).stdout == ""


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
    commit_all(project)
    project.write("api/src/a.py", "x\n")
    project.write("api/tests/test_a.py", "x\n")
    assert run(project).stdout == ""
    assert not (project.root / "web" / "w.marker").exists()


def test_three_blocks_then_gives_up(project: Project) -> None:
    commit_all(project)
    project.write("api/src/app.py", "x = 1\n")
    for n in (1, 2, 3):
        reason(run(project))
        assert counter(project) == n
    proc = run(project)
    assert proc.returncode == 0 and proc.stdout == ""
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
