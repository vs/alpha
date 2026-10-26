"""Commit a generated skeleton in a few convention-following commits."""

import subprocess
from pathlib import Path
from typing import Any

from alpha.generate import GenerateError
from alpha.render.ci import DEPENDABOT, WORKFLOW

HOOKS_PATH = ".claude/alpha/githooks"
_DOCS = [
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "docs",
    ".gitignore",
]
_CLAUDE = ["CLAUDE.md", ".claude"]
_CI = ".github"
_MAX_DESCRIPTION = 50  # the commit-msg hook's limit


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


def _check_identity(target: Path) -> None:
    """Fail before committing when git would have to guess the author."""
    for role in ("AUTHOR", "COMMITTER"):
        done = _git(target, "-c", "user.useConfigOnly=true", "var", f"GIT_{role}_IDENT")
        if done.returncode != 0:
            raise GenerateError(
                "git doesn't know who you are, so the skeleton's commits would "
                "carry a guessed author (like you@your-mac.local). Set your "
                'identity with git config --global user.name "Your Name" and '
                'git config --global user.email "you@example.com", then rerun '
                f'"alpha commit-skeleton {target}".'
            )


def _build_subject(component: dict[str, Any], scopes: list[str]) -> str:
    """The component's build commit; scoped only when the hook accepts the scope."""
    name, stack = component["name"], component["stack"]
    if not scopes or name in scopes:
        return f"build({name}): Set up {stack} toolchain and tests"
    description = f"Set up {name} toolchain and tests"
    if len(description) > _MAX_DESCRIPTION:
        description = f"Set up {stack} toolchain and tests"
    return f"build: {description}"


def commit_skeleton(
    target: Path, principles: dict[str, Any], trailers: list[str]
) -> list[str]:
    """Commit docs, Claude settings, each component, then CI; return the hashes."""
    if not (target / ".git").exists():
        _check(target, "init", "-q", "-b", "main")
    _check(target, "config", "core.hooksPath", HOOKS_PATH)
    _check_identity(target)
    groups = [
        ("docs: Add product brief, principles and decisions", _DOCS),
        ("chore: Add Claude Code settings and guardrails", _CLAUDE),
    ]
    scopes = [str(s) for s in principles.get("git", {}).get("scopes", [])]
    for c in principles["components"]:
        paths = [c["path"]]
        if c["path"] == ".":  # the root takes the rest, except the CI commit's
            paths.append(f":(exclude){_CI}")
        groups.append((_build_subject(c, scopes), paths))
    groups.append(("ci: Run every component's checks in CI", [WORKFLOW]))
    groups.append(("ci: Schedule dependency updates", [DEPENDABOT]))

    hashes: list[str] = []
    for subject, paths in groups:
        present = [p for p in paths if p.startswith(":(") or (target / p).exists()]
        if all(p.startswith(":(") for p in present):
            continue  # none of the group's own paths exist
        _check(target, "add", "-A", "--", *present)
        # Only this group's paths: a failed earlier run may have left others staged.
        staged = _git(target, "diff", "--cached", "--quiet", "--", *present)
        if staged.returncode == 0:
            continue  # nothing staged for this group
        if staged.returncode != 1:
            _check(target, "diff", "--cached", "--quiet", "--", *present)  # the error
        message = subject + ("\n\n" + "\n".join(trailers) if trailers else "")
        _check(target, "commit", "-q", "-m", message, "--", *present)
        hashes.append(_check(target, "rev-parse", "HEAD"))
    return hashes
