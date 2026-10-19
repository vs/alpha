"""Commit a generated skeleton in a few convention-following commits."""

import subprocess
from pathlib import Path
from typing import Any

from alpha.generate import GenerateError

HOOKS_PATH = ".claude/alpha/githooks"
_DOCS = ["README.md", "LICENSE", "CONTRIBUTING.md", "docs", ".gitignore"]
_CLAUDE = ["CLAUDE.md", ".claude"]


def _git(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args], cwd=target, capture_output=True, text=True
        )
    except OSError as e:
        raise GenerateError(
            f'Cannot run git ({e}). Install git, then rerun "alpha commit-skeleton '
            f'{target}".'
        ) from e


def _check(target: Path, *args: str) -> str:
    done = _git(target, *args)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip()
        raise GenerateError(
            f"git {args[0]} failed in {target}: {detail}\n"
            f'Fix that, then rerun "alpha commit-skeleton {target}".'
        )
    return done.stdout.strip()


def commit_skeleton(
    target: Path, principles: dict[str, Any], trailers: list[str]
) -> list[str]:
    """Commit docs, Claude settings, then each component; return the hashes."""
    if not (target / ".git").exists():
        _check(target, "init", "-q", "-b", "main")
    _check(target, "config", "core.hooksPath", HOOKS_PATH)
    groups = [
        ("docs: Add product brief, principles and decisions", _DOCS),
        ("chore: Add Claude Code settings and guardrails", _CLAUDE),
    ]
    for c in principles["components"]:
        subject = f"build({c['name']}): Set up {c['stack']} toolchain and tests"
        groups.append((subject, [c["path"]]))  # "." takes everything left

    hashes: list[str] = []
    for subject, paths in groups:
        present = [p for p in paths if (target / p).exists()]
        if not present:
            continue
        _check(target, "add", "-A", "--", *present)
        staged = _git(target, "diff", "--cached", "--quiet").returncode
        if staged == 0:
            continue  # nothing staged for this group
        if staged != 1:
            _check(target, "diff", "--cached", "--quiet")  # report git's error
        message = subject + ("\n\n" + "\n".join(trailers) if trailers else "")
        _check(target, "commit", "-q", "-m", message)
        hashes.append(_check(target, "rev-parse", "HEAD"))
    return hashes
