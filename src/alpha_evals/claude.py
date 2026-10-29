"""One headless `claude -p` call, parsed from its JSON result."""

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

_TAIL = 5


@dataclass(frozen=True)
class Turn:
    session_id: str
    text: str
    cost_usd: float
    denials: tuple[dict[str, Any], ...]
    ok: bool
    error: str = ""


def _failed(error: str) -> Turn:
    return Turn("", "", 0.0, (), False, error)


def run_claude(
    claude: Sequence[str],
    args: Sequence[str],
    prompt: str,
    cwd: Path,
    env: Mapping[str, str],
    resume: str | None = None,
    timeout: float = 1800,
) -> Turn:
    """Run claude -p with the prompt on stdin (a reply may start with "-")."""
    command = [
        *claude,
        "-p",
        *(["--resume", resume] if resume else []),
        "--output-format",
        "json",
        "--setting-sources",
        "project,local",
        *args,
    ]
    try:
        done = subprocess.run(
            command,
            input=prompt,
            cwd=cwd,
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _failed(f"timeout after {timeout:g}s")
    except OSError as e:
        return _failed(f"can't run {claude[0]}: {e}")
    if done.returncode != 0:
        tail = " | ".join(done.stderr.strip().splitlines()[-_TAIL:])
        return _failed(f"exit {done.returncode}: {tail or '(no stderr)'}")
    try:
        data: object = json.loads(done.stdout)
    except ValueError:
        return _failed(f"not JSON: {done.stdout.strip()[:200]}")
    if not isinstance(data, dict):
        return _failed(f"not JSON: {done.stdout.strip()[:200]}")
    out = cast(dict[str, Any], data)
    text = str(out.get("result", ""))
    cost = float(out.get("total_cost_usd") or 0.0)
    denials = tuple(cast(list[dict[str, Any]], out.get("permission_denials") or []))
    session = str(out.get("session_id", ""))
    subtype = str(out.get("subtype", ""))
    if out.get("is_error") or subtype != "success":
        return Turn(session, text, cost, denials, False, f"{subtype}: {text[:200]}")
    return Turn(session, text, cost, denials, True)
