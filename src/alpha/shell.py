"""Running a tool's command under a time limit."""

import os
import signal
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

GIT_TIMEOUT = 120.0  # seconds: a git command (and its hooks) that runs longer is stuck


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
