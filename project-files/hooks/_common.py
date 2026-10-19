"""Shared helpers for alpha's Claude Code hooks (stdlib only).

Must parse and import on Python 3.9 (no 3.10+ syntax, no runtime `X | Y`; annotations
are lazy), so that `check_python()` can print its guard message, not a SyntaxError.
"""

from __future__ import annotations

import fnmatch
import json
import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

STATE_DIR = ".claude/alpha/state"
NOT_FOUND = 127
TAIL_LINES = 60


class TimedOut(Exception):
    pass


def check_python() -> None:
    if sys.version_info < (3, 11):  # noqa: UP036 (hooks run on whatever python3 exists)
        found = "{}.{}".format(*sys.version_info[:2])
        print(
            f"alpha needs Python 3.11+ (found {found}). Install a newer one with "
            '"brew install python" or "uv python install 3.12", then retry.',
            file=sys.stderr,
        )
        sys.exit(0)


def read_input() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError as e:
        print(
            f"alpha: hook input is not valid JSON ({e}); ignoring it. "
            "Check the hook wiring in .claude/settings.json.",
            file=sys.stderr,
        )
        return {}
    if not isinstance(data, dict):
        print("alpha: hook input is not a JSON object; ignoring it.", file=sys.stderr)
        return {}
    return data  # pyright: ignore[reportUnknownVariableType]


def project_root(inp: dict[str, Any]) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    cwd = inp.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd)
    return Path.cwd()


def load_principles(root: Path) -> dict[str, Any] | None:
    path = root / "docs" / "principles.toml"
    if not path.is_file():
        return None
    import tomllib  # lazy: absent on 3.9, and check_python() has exited by then

    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        print(
            f"docs/principles.toml is not valid TOML: {e}. Fix the file (it is the "
            "single source of truth for alpha's checks), or restore it with "
            '"git checkout docs/principles.toml".',
            file=sys.stderr,
        )
        sys.exit(0)


def component_for(rel_path: str, principles: dict[str, Any]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_len = -1
    for comp in principles.get("components", []):
        base = str(comp.get("path", ".")).strip("/")
        if base in ("", "."):
            length = 0
        elif rel_path == base or rel_path.startswith(base + "/"):
            length = len(base)
        else:
            continue
        if length > best_len:
            best, best_len = comp, length
    return best


def changed_files(root: Path) -> list[str]:
    """Tracked changes vs HEAD plus untracked files, minus alpha's own state dir."""
    fix = "Make sure this is a git repository (git init) and git is installed."
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        print(f"alpha: could not run git in {root}: {e}. {fix}", file=sys.stderr)
        return []
    if proc.returncode != 0:
        print(
            f"alpha: could not list changes in {root}: {proc.stderr.strip()}. {fix}",
            file=sys.stderr,
        )
        return []
    entries = proc.stdout.split("\0")
    files: list[str] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            i += 1  # the next entry is the rename source
        if path.startswith(STATE_DIR + "/"):
            continue
        files.append(path)
    return files


def _match_parts(path: list[str], pat: list[str]) -> bool:
    if not pat:
        return not path
    if pat[0] == "**":
        return any(_match_parts(path[k:], pat[1:]) for k in range(len(path) + 1))
    if not path:
        return False
    return fnmatch.fnmatchcase(path[0], pat[0]) and _match_parts(path[1:], pat[1:])


def matches(rel_path: str, globs: list[str]) -> bool:
    parts = rel_path.split("/")
    return any(_match_parts(parts, g.split("/")) for g in globs)


def rel_to_root(root: Path, path: str) -> str | None:
    """POSIX path of `path` (absolute, or relative to root) under root, else None."""
    base = root.resolve()
    p = Path(path)
    try:
        return (
            (p if p.is_absolute() else base / p).resolve().relative_to(base).as_posix()
        )
    except ValueError:
        return None


def block(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(2)


def state_path(root: Path, name: str) -> Path:
    directory = root / STATE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory / name


def run_command(command: str, cwd: Path, timeout: float) -> tuple[int, str]:
    """(exit code, combined output). Raises TimedOut after `timeout` seconds."""
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
        out, _ = proc.communicate(timeout=timeout)
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
