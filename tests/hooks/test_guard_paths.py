import json
import subprocess
from typing import Any

from .conftest import Project


def run(
    project: Project, tool: str, tool_input: dict[str, Any]
) -> subprocess.CompletedProcess[str]:
    return project.run_hook(
        "guard_paths.py", {"tool_name": tool, "tool_input": tool_input}
    )


def edit(
    project: Project, rel: str, old: str, new: str
) -> subprocess.CompletedProcess[str]:
    path = str(project.root / rel)
    return run(
        project, "Edit", {"file_path": path, "old_string": old, "new_string": new}
    )


def reason(proc: subprocess.CompletedProcess[str]) -> str:
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "ask"
    return out["permissionDecisionReason"]


def test_lockfile_blocked_with_component_setup_command(project: Project) -> None:
    project.set_commands("api", setup="uv sync")
    proc = run(project, "Write", {"file_path": str(project.root / "api/uv.lock")})
    assert proc.returncode == 2
    assert proc.stderr.startswith(
        "api/uv.lock is protected (`api/uv.lock` in docs/principles.toml), so "
        "Claude can't edit it."
    )
    assert "Lockfiles change only through the package manager (e.g. uv sync)." in (
        proc.stderr
    )
    assert "Secrets" not in proc.stderr


def test_env_local_blocked_as_a_secret(project: Project) -> None:
    proc = run(project, "Write", {"file_path": str(project.root / ".env.local")})
    assert proc.returncode == 2
    assert ".env.local is protected (`**/.env.*` in" in proc.stderr
    assert "Secrets belong in the environment" in proc.stderr
    assert "Lockfiles" not in proc.stderr


def test_extra_protected_path_asks_for_a_hand_edit(project: Project) -> None:
    proc = run(project, "Write", {"file_path": str(project.root / "api/keys/a.txt")})
    assert proc.returncode == 2
    assert "api/keys/a.txt is protected (`api/keys/**` in" in proc.stderr
    assert "Ask the user to change it by hand." in proc.stderr
    assert "Lockfiles" not in proc.stderr and "Secrets" not in proc.stderr


def test_unprotected_file_passes(project: Project) -> None:
    proc = edit(project, "api/src/app.py", "a", "b")
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_path_outside_root_passes(project: Project) -> None:
    proc = run(project, "Write", {"file_path": "/tmp/elsewhere/.env"})
    assert proc.returncode == 0


def test_other_tools_ignored(project: Project) -> None:
    proc = run(project, "Read", {"file_path": str(project.root / ".env")})
    assert proc.returncode == 0


def test_non_alpha_project_passes(tmp_path: Any) -> None:
    import subprocess as sp
    import sys

    from .conftest import HOOKS

    proc = sp.run(
        [sys.executable, str(HOOKS / "guard_paths.py")],
        input=json.dumps(
            {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / ".env")}}
        ),
        env={"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert proc.stderr == ""


def test_adding_type_ignore_asks(project: Project) -> None:
    proc = edit(project, "api/a.py", "x = f()", "x = f()  # type: ignore")
    assert proc.returncode == 0
    assert reason(proc) == (
        "This edit weakens a check (# type: ignore). Principle never-weaken-checks: "
        "fix the cause instead, or approve if you are sure."
    )


def test_editing_line_that_already_has_pattern_passes(project: Project) -> None:
    proc = edit(
        project, "api/a.py", "x = f()  # type: ignore", "x = g()  # type: ignore"
    )
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_adding_second_instance_asks(project: Project) -> None:
    proc = edit(
        project,
        "api/a.py",
        "x = f()  # type: ignore",
        "x = f()  # type: ignore\ny = g()  # type: ignore",
    )
    assert "# type: ignore" in reason(proc)


def test_multiple_patterns_listed(project: Project) -> None:
    proc = edit(project, "api/a.py", "x", "x  # noqa\ny  # pyright: ignore")
    r = reason(proc)
    assert "(# pyright: ignore, # noqa)" in r or "(# noqa, # pyright: ignore)" in r


def test_except_pass_whitespace_insensitive(project: Project) -> None:
    proc = edit(project, "api/a.py", "x", "try:\n    f()\nexcept Exception:\n    pass")
    assert "except Exception: pass" in reason(proc)
    proc = edit(project, "api/a.py", "x", "try:\n    f()\nexcept:  pass")
    assert "except: pass" in reason(proc)


def test_write_compares_against_existing_content(project: Project) -> None:
    project.write("web/a.ts", "// @ts-ignore\nlet a = 1\n")
    path = str(project.root / "web/a.ts")
    same = run(
        project, "Write", {"file_path": path, "content": "// @ts-ignore\nlet a = 2\n"}
    )
    assert same.stdout == ""
    more = run(
        project,
        "Write",
        {"file_path": path, "content": "// @ts-ignore\n// @ts-ignore\n"},
    )
    assert "@ts-ignore" in reason(more)


def test_write_new_file_with_pattern_asks(project: Project) -> None:
    path = str(project.root / "web/new.ts")
    proc = run(project, "Write", {"file_path": path, "content": 'x: "strict": false'})
    assert '"strict": false' in reason(proc)


def test_multiedit_sums_edits(project: Project) -> None:
    path = str(project.root / "api/a.py")
    edits = [
        {"old_string": "a", "new_string": "a  # noqa"},
        {"old_string": "b", "new_string": "b  # noqa"},
    ]
    proc = run(project, "MultiEdit", {"file_path": path, "edits": edits})
    assert "# noqa" in reason(proc)
    edits = [{"old_string": "a  # noqa", "new_string": "c  # noqa"}]
    proc = run(project, "MultiEdit", {"file_path": path, "edits": edits})
    assert proc.stdout == ""


def test_block_wins_over_weakening(project: Project) -> None:
    proc = run(
        project,
        "Write",
        {"file_path": str(project.root / ".env"), "content": "# noqa"},
    )
    assert proc.returncode == 2
    assert proc.stdout == ""


def test_identifier_lookalikes_pass(project: Project) -> None:
    for new in (
        "sys.exit(1)",
        "os._exit(0)",
        "exit(0)",
        "wait.skip(x)",
        "latest.skip(1)",
    ):
        assert edit(project, "api/a.py", "x", new).stdout == "", new


def test_test_skip_calls_at_identifier_boundary_ask(project: Project) -> None:
    assert "xit(" in reason(edit(project, "web/a.ts", "x", "xit('a', f)"))
    assert "it.skip(" in reason(edit(project, "web/a.ts", "x", "a\n  it.skip('a')"))
    assert "test.skip(" in reason(edit(project, "web/a.ts", "x", "test.skip('a')"))


def test_dropped_never_weaken_checks_does_not_ask(project: Project) -> None:
    project.drop_principle("never-weaken-checks", component="api")
    proc = edit(project, "api/src/app.py", "x = 1", "x = 1  # noqa")
    assert proc.returncode == 0 and proc.stdout == ""
    proc = edit(project, "web/src/app.ts", "x", "x // biome-ignore")
    assert "biome-ignore" in reason(proc)


def test_nested_env_files_blocked(project: Project) -> None:
    for rel in ("api/.env", "web/config/.env.local"):
        proc = run(project, "Write", {"file_path": str(project.root / rel)})
        assert proc.returncode == 2, rel
        assert f"{rel} is protected (" in proc.stderr
        assert "Secrets belong in the environment" in proc.stderr


def test_principles_file_edit_asks(project: Project) -> None:
    proc = edit(project, "docs/principles.toml", 'test = "x"', 'test = "true"')
    assert proc.returncode == 0
    text = reason(proc)
    assert "docs/principles.toml" in text
    assert "single source of truth" in text
    write = run(
        project,
        "Write",
        {"file_path": str(project.root / "docs/principles.toml"), "content": ""},
    )
    assert "single source of truth" in reason(write)


def test_the_review_state_is_not_editable(project: Project) -> None:
    path = str(project.root / ".claude/alpha/state/review.json")
    proc = run(project, "Write", {"file_path": path})
    assert proc.returncode == 2
    assert "alpha's hooks keep their state there" in proc.stderr
