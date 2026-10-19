"""PostToolUse hook for Edit|Write|MultiEdit: formats then lints the edited file."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402

TOOLS = {"Edit", "Write", "MultiEdit"}
TIMEOUT = 60
TAIL_LINES = 60
NOT_FOUND = 127


class TimedOut(Exception):
    pass


def run_command(command: str, cwd: Path) -> tuple[int, str]:
    """(exit code, combined output). Raises TimedOut after TIMEOUT seconds."""
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except OSError as err:
        return NOT_FOUND, str(err)
    try:
        out, _ = proc.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        proc.communicate()
        raise TimedOut from None
    return proc.returncode, out


def tail(output: str) -> str:
    return "\n".join(output.rstrip("\n").splitlines()[-TAIL_LINES:])


def first_word(command: str) -> str:
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    return words[0] if words else command


def main() -> None:
    _common.check_python()
    inp = _common.read_input()
    root = _common.project_root(inp)
    principles = _common.load_principles(root)
    if principles is None:
        sys.exit(0)
    tool = inp.get("tool_name")
    tool_input: object = inp.get("tool_input")
    if tool not in TOOLS or not isinstance(tool_input, dict):
        sys.exit(0)
    args: dict[str, Any] = tool_input  # pyright: ignore[reportUnknownVariableType]
    file_path = args.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        sys.exit(0)
    rel = _common.rel_to_root(root, file_path)
    if rel is None:
        sys.exit(0)
    comp = _common.component_for(rel, principles)
    if comp is None:
        sys.exit(0)
    globs: list[str] = list(comp.get("source_globs", [])) + list(
        comp.get("test_globs", [])
    )
    if not _common.matches(rel, globs):
        sys.exit(0)
    commands: dict[str, Any] = comp.get("commands", {})
    base = str(comp.get("path", ".")).strip("/")
    cwd = root if base in ("", ".") else root / base
    in_comp = rel if cwd == root else rel[len(base) + 1 :]
    quoted = shlex.quote(in_comp)
    name = str(comp.get("name", base))

    for key in ("format_file", "lint_file"):
        template = commands.get(key)
        if not isinstance(template, str) or not template:
            continue
        command = template.replace("{file}", quoted)
        try:
            code, output = run_command(command, cwd)
        except TimedOut:
            _common.block(
                f"{command} took longer than {TIMEOUT}s on {rel}. Run it by hand "
                "to see why, or tell the user."
            )
        if code == NOT_FOUND:
            setup = commands.get("setup") or "the component's setup step"
            _common.block(
                f"{first_word(command)} is not installed for component {name}. "
                f"Run its setup command: {setup}"
            )
        if code != 0:
            advice = (
                f"Formatting failed for {rel}. Fix the syntax error above."
                if key == "format_file"
                else f"Fix the lint errors above in {rel}."
            )
            _common.block(f"{tail(output)}\n{advice}")
    sys.exit(0)


if __name__ == "__main__":
    main()
