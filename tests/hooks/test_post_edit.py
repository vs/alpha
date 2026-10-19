import subprocess
from typing import Any

from .conftest import Project

LINT_FAIL = "python3 -c \"import sys; print('E1 bad'); sys.exit(1)\""


def run(
    project: Project, rel: str, tool: str = "Edit"
) -> subprocess.CompletedProcess[str]:
    target = project.root / rel
    if project.root in target.resolve().parents:
        target.parent.mkdir(parents=True, exist_ok=True)  # the edit created it
    tool_input: dict[str, Any] = {"file_path": str(target)}
    return project.run_hook(
        "post_edit.py",
        {"tool_name": tool, "tool_input": tool_input, "tool_response": {}},
    )


def marker_cmd(name: str) -> str:
    # Records its {file} argument (already shell-quoted by the hook) in a marker.
    return f"python3 -c \"import sys; open('{name}', 'a').write(sys.argv[1] + '|')\""


def test_lint_failure_blocks_with_output(project: Project) -> None:
    project.set_commands("api", lint_file=LINT_FAIL)
    proc = run(project, "api/src/app.py")
    assert proc.returncode == 2
    assert "E1 bad" in proc.stderr
    assert "Fix the lint errors above in api/src/app.py." in proc.stderr


def test_format_runs_before_lint_in_component_dir(project: Project) -> None:
    project.set_commands(
        "api",
        format_file=marker_cmd("fmt.marker") + " {file}",
        lint_file=marker_cmd("lint.marker") + " {file}",
    )
    proc = run(project, "api/src/app.py", tool="Write")
    assert proc.returncode == 0
    assert (project.root / "api" / "fmt.marker").read_text() == "src/app.py|"
    assert (project.root / "api" / "lint.marker").read_text() == "src/app.py|"


def test_file_is_shell_quoted(project: Project) -> None:
    project.set_commands("api", format_file=marker_cmd("fmt.marker") + " {file}")
    assert run(project, "api/src/my app.py").returncode == 0
    assert (project.root / "api" / "fmt.marker").read_text() == "src/my app.py|"


def test_test_glob_files_are_checked(project: Project) -> None:
    project.set_commands("api", lint_file=LINT_FAIL)
    assert run(project, "api/tests/test_x.py").returncode == 2


def test_unmatched_file_runs_nothing(project: Project) -> None:
    project.set_commands("api", format_file=marker_cmd("fmt.marker") + " x")
    proc = run(project, "api/README.md")
    assert proc.returncode == 0
    assert not (project.root / "api" / "fmt.marker").exists()


def test_outside_component_and_root_pass(project: Project) -> None:
    assert run(project, "README.md").returncode == 0
    assert run(project, "../elsewhere/x.py").returncode == 0


def test_other_tools_ignored(project: Project) -> None:
    project.set_commands("api", lint_file=LINT_FAIL)
    assert run(project, "api/src/app.py", tool="Read").returncode == 0


def test_exit_127_gives_setup_hint(project: Project) -> None:
    project.set_commands("api", lint_file="sh -c 'exit 127'", setup="uv sync")
    proc = run(project, "api/src/app.py")
    assert proc.returncode == 2
    assert "sh is not installed for component api. Run its setup command: uv sync" in (
        proc.stderr
    )


def test_missing_command_gives_setup_hint(project: Project) -> None:
    project.set_commands("api", format_file="nonexistent-tool-xyz {file}", setup="s")
    proc = run(project, "api/src/app.py")
    assert proc.returncode == 2
    assert (
        "nonexistent-tool-xyz is not installed for component api. "
        "Run its setup command: s"
    ) in proc.stderr


def test_format_failure_blocks_and_skips_lint(project: Project) -> None:
    project.set_commands(
        "api",
        format_file="python3 -c \"import sys; print('syntax error'); sys.exit(1)\"",
        lint_file=marker_cmd("lint.marker") + " x",
    )
    proc = run(project, "api/src/app.py")
    assert proc.returncode == 2
    assert "syntax error" in proc.stderr
    assert (
        "Formatting failed for api/src/app.py. Fix the syntax error above."
        in proc.stderr
    )
    assert not (project.root / "api" / "lint.marker").exists()


def test_output_tail_is_last_60_lines(project: Project) -> None:
    project.set_commands(
        "api",
        lint_file='python3 -c "import sys; '
        "print('\\n'.join(f'L{i}' for i in range(100))); sys.exit(1)\"",
    )
    proc = run(project, "api/src/app.py")
    assert "L99" in proc.stderr and "L40" in proc.stderr
    assert "L39\n" not in proc.stderr


def test_timeout_blocks_naming_command(project: Project, monkeypatch: Any) -> None:
    import post_edit

    monkeypatch.setattr(post_edit, "TIMEOUT", 1)
    code = None
    try:
        post_edit.run_command("sleep 5", project.root)
    except post_edit.TimedOut:
        code = "timeout"
    assert code == "timeout"
