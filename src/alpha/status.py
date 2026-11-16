"""What state a folder is in, for /alpha:install to take the matching path."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from alpha.answers import AnswersError, next_step, parse_answers, read_project_json
from alpha.merge import is_alpha_hook
from alpha.shell import git_output

HOOKS_PATH = ".claude/alpha/githooks"
SETTINGS = ".claude/settings.json"
CHAIN_STATE = ".claude/alpha/state/chain.json"
ADOPT_BRANCH = "alpha/adopt"
# What an empty folder may hold: macOS litter and Claude Code's local settings.
_IGNORED = frozenset({".DS_Store", ".git", ".claude/settings.local.json"})


@dataclass(frozen=True)
class Status:
    name: str
    detail: str = ""


def _entries(target: Path) -> list[str]:
    found: list[str] = []
    for entry in target.iterdir():
        rel = entry.name
        if rel in _IGNORED:
            continue
        if rel == ".claude" and entry.is_dir():
            found += [
                f".claude/{p.name}"
                for p in entry.iterdir()
                if f".claude/{p.name}" not in _IGNORED
            ]
            continue
        found.append(rel)
    return sorted(found)


def _hooks_wired(target: Path) -> bool:
    try:
        settings: object = json.loads((target / SETTINGS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    hooks: object = (
        cast(dict[str, object], settings).get("hooks")
        if isinstance(settings, dict)
        else None
    )
    if not isinstance(hooks, dict):
        return False
    for groups in cast(dict[str, object], hooks).values():
        for group in cast(list[object], groups) if isinstance(groups, list) else []:
            entries: object = (
                cast(dict[str, object], group).get("hooks")
                if isinstance(group, dict)
                else None
            )
            items = cast(list[object], entries) if isinstance(entries, list) else []
            if any(is_alpha_hook(h) for h in items):
                return True
    return False


def hooks_off(target: Path, answers: dict[str, Any]) -> list[str]:
    """What's switched off of alpha's hooks in an installed project."""
    off: list[str] = []
    if not _hooks_wired(target):
        off.append(f"alpha's hook entries in {SETTINGS}")
    adoption: object = answers.get("adoption")
    chained = (
        isinstance(adoption, dict)
        and cast(dict[str, Any], adoption).get("git_hooks") == "chain"
    )
    if chained:
        if (target / CHAIN_STATE).is_file():
            off.append("alpha's call from the hook manager's commit-msg hook")
    elif git_output(target, "config", "--get", "core.hooksPath") != HOOKS_PATH:
        off.append(f"core.hooksPath ({HOOKS_PATH})")
    return off


def _next_step(target: Path, answers: dict[str, Any]) -> str:
    """What /alpha:install does next in an adopted repo: the step alpha adopt
    next names. Nothing when the answers don't parse; adopt next says why."""
    try:
        steps = parse_answers(answers, target, proven=False).steps
    except AnswersError:
        return ""
    found, _ = next_step(steps)
    return f"the adoption plan's next step is {found.id}" if found else ""


def status(target: Path) -> Status:
    if not target.is_dir():
        return Status("missing", f"{target} isn't a folder; create it first")
    try:
        answers = read_project_json(target)
    except AnswersError:
        answers = None  # routes like a folder without one; install says why
    if answers is not None and "installed" in answers:
        off = hooks_off(target, answers)
        if off:
            return Status("hooks-off", "switched off: " + ", ".join(off))
        return Status("installed", _next_step(target, answers))
    if answers is not None and "manifest" in answers:
        return Status(
            "old-kit",
            "an older alpha set it up; follow the by-hand steps in alpha's README",
        )
    if answers is not None:
        return Status("interview", "an interview is under way; it resumes")
    entries = _entries(target)
    top = git_output(target, "rev-parse", "--show-toplevel")
    in_repo = top is not None
    head = (
        git_output(target, "rev-parse", "--verify", "-q", "HEAD") if in_repo else None
    )
    inside_another = top is not None and Path(top).resolve() != target.resolve()
    if not entries and (head is None or inside_another):
        return Status("empty")
    if not in_repo:
        return Status(
            "not-a-repo", "run git init and commit the files, then install again"
        )
    if head is None:
        return Status("uncommitted", "commit the files, then install again")
    branch = git_output(target, "branch", "--show-current") or ""
    if not branch:
        return Status("uncommitted", "HEAD is detached; switch to a branch first")
    if git_output(target, "status", "--porcelain"):
        return Status("uncommitted", "commit or stash the changes first")
    if branch != ADOPT_BRANCH and git_output(
        target, "rev-parse", "--verify", "-q", f"refs/heads/{ADOPT_BRANCH}"
    ):
        return Status(
            "adopting", f"switch to it (git switch {ADOPT_BRANCH}) and install again"
        )
    return Status("existing")
