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
    out = _parse(done.stdout)
    if done.returncode != 0:
        if out is not None:  # JSON mode reports its own failures on stdout
            failed = _turn(out)
            reason = failed.error or f"{failed.text[:200]}"
            return Turn(
                failed.session_id,
                failed.text,
                failed.cost_usd,
                failed.denials,
                False,
                f"exit {done.returncode}: {reason}",
            )
        stream = done.stderr.strip() or done.stdout.strip()
        tail = " | ".join(stream.splitlines()[-_TAIL:])
        return _failed(f"exit {done.returncode}: {tail or '(no output)'}")
    if out is None:
        return _failed(f"not JSON: {done.stdout.strip()[:200]}")
    return _turn(out)


def _parse(stdout: str) -> dict[str, Any] | None:
    try:
        data: object = json.loads(stdout)
    except ValueError:
        return None
    return cast(dict[str, Any], data) if isinstance(data, dict) else None


def _turn(out: dict[str, Any]) -> Turn:
    text = str(out.get("result", ""))
    cost = float(out.get("total_cost_usd") or 0.0)
    denials = tuple(cast(list[dict[str, Any]], out.get("permission_denials") or []))
    session = str(out.get("session_id", ""))
    subtype = str(out.get("subtype", ""))
    if out.get("is_error") or subtype != "success":
        return Turn(session, text, cost, denials, False, f"{subtype}: {text[:200]}")
    return Turn(session, text, cost, denials, True)
