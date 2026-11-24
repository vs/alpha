"""Running a tool's command under a time limit."""

import os
import signal
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

GIT_TIMEOUT = 120.0  # seconds: a git command (and its hooks) that runs longer is stuck


class GitError(Exception):
    """git couldn't start, or ran longer than GIT_TIMEOUT."""


def git(
    target: Path,
    *args: str,
    stdin: str | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """git `args` in `target`, under GIT_TIMEOUT, with paths in its output
    left unquoted and no signature checks mixed into log or show output."""
    try:
        return subprocess.run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "-c",
                "log.showSignature=false",
                *args,
            ],
            cwd=target,
            input=stdin,
            capture_output=True,
            encoding="utf-8",
            timeout=GIT_TIMEOUT,
            env={**os.environ, **env} if env else None,
        )
    except OSError as e:
        raise GitError(f"Cannot run git ({e}). Install git, then retry.") from e
    except subprocess.TimeoutExpired:
        raise GitError(
            f"git {args[0]} took longer than {GIT_TIMEOUT:g}s in {target}, so alpha "
            "stopped it. Run it yourself to see what it waits for, then retry."
        ) from None


def git_output(target: Path, *args: str) -> str | None:
    """git's stripped output, or None when it fails or can't run."""
    try:
        done = git(target, *args)
    except GitError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


@dataclass(frozen=True)
class Ran:
    code: int
    out: str
    err: str  # "" when stderr was merged into out


def run_command(
    command: str | Sequence[str],
    cwd: Path,
    timeout: float,
    *,
    merge: bool = True,
    env: Mapping[str, str] | None = None,
) -> Ran | None:
    """Run `command` (a shell line, or an argv list) with no stdin, so a prompt
    fails instead of waiting. After `timeout` seconds its whole process group
    is killed and the result is None. Raises OSError when it can't start."""
    proc = subprocess.Popen(
        command,
        shell=isinstance(command, str),
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge else subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return None
    return Ran(proc.returncode, out, err or "")
