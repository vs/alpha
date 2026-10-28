"""Commit a generated skeleton in a few convention-following commits."""

import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from alpha.answers import PROJECT_JSON
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
UPDATE_STATE = ".claude/alpha/state/update.json"  # written by alpha update
PROPOSALS = ".claude/alpha/state/update"  # its proposals for conflicting files
_REVIEW = ".claude/alpha/hooks/review.py"
_CI = ".github"
_MAX_DESCRIPTION = 50  # the commit-msg hook's limit


def commit_group(path: str, component_of: Mapping[str, str]) -> str:
    """The commit a changed file belongs in, by what made it."""
    if path in component_of:
        return f"build:{component_of[path]}"
    if path == WORKFLOW:
        return "ci"
    if path == DEPENDABOT:
        return "dependabot"
    if path == "CLAUDE.md" or path.startswith(".claude/"):
        return "chore"
    return "docs"


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

    return _commit_groups(target, groups, trailers)


def _commit_groups(
    target: Path, groups: list[tuple[str, list[str]]], trailers: list[str]
) -> list[str]:
    """One commit per group that has changes in its paths; return the hashes."""
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


def _update_subject(name: str, scopes: list[str]) -> str:
    """An existing component's update commit; scoped only when the hook accepts it."""
    if not scopes or name in scopes:
        return f"build({name}): Update toolchain settings"
    description = f"Update {name} toolchain settings"
    if len(description) > _MAX_DESCRIPTION:
        description = "Update toolchain settings"
    return f"build: {description}"


def _absorb_review(target: Path, before_tree: str) -> bool:
    """Tell the review hook alpha's changes are not Claude's; False if it can't."""
    script = target / _REVIEW
    if not script.is_file():
        return False
    try:
        done = subprocess.run(
            ["python3", str(script), "absorb", before_tree],
            cwd=target,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return done.returncode == 0


def commit_update(
    target: Path, principles: dict[str, Any], trailers: list[str]
) -> tuple[list[str], list[str]]:
    """Commit the files alpha update wrote, in groups; return (hashes, notes)."""
    state_file = target / UPDATE_STATE
    if not state_file.is_file():
        raise GenerateError(f"Nothing to commit: run alpha update {target} first.")
    try:
        state: dict[str, Any] = json.loads(state_file.read_text(encoding="utf-8"))
        by_group: dict[str, str] = state["groups"]
        new_components: list[str] = state["new_components"]
        conflicts: dict[str, str] = state["conflicts"]
    except (OSError, ValueError, KeyError, TypeError):
        raise GenerateError(
            f"{state_file} is unreadable. Delete it and {target / PROPOSALS}, "
            f"then run alpha update {target} again."
        ) from None
    _check_identity(target)

    def paths_of(group: str) -> list[str]:
        return sorted(p for p, g in by_group.items() if g == group)

    scopes = [str(s) for s in principles.get("git", {}).get("scopes", [])]
    groups: list[tuple[str, list[str]]] = [
        ("docs: Update docs and decision records", paths_of("docs")),
        (
            "chore: Update Claude Code rules and settings",
            [*paths_of("chore"), PROJECT_JSON],  # the moved baseline always changes
        ),
    ]
    for c in principles["components"]:
        if c["name"] in new_components:
            paths = [c["path"]]
            if c["path"] == ".":
                paths.append(f":(exclude){_CI}")
            groups.append((_build_subject(c, scopes), paths))
        else:
            groups.append(
                (_update_subject(c["name"], scopes), paths_of(f"build:{c['name']}"))
            )
    groups += [
        ("ci: Update the CI checks", paths_of("ci")),
        ("ci: Update the dependency update schedule", paths_of("dependabot")),
    ]
    hashes = _commit_groups(target, [g for g in groups if g[1]], trailers)

    notes = [
        f"{path}: alpha's change wasn't merged in (proposal: {PROPOSALS}/{path})."
        for path, recorded in sorted(conflicts.items())
        if hashlib.sha256((target / path).read_bytes()).hexdigest() == recorded
    ]
    before = state.get("before_tree")
    if isinstance(before, str) and not _absorb_review(target, before):
        notes.append("The reviewer will look at alpha's changes at the next Stop.")
    state_file.unlink()
    shutil.rmtree(target / PROPOSALS, ignore_errors=True)
    return hashes, notes
