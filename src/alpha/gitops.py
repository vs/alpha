import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from alpha.answers import PROJECT_JSON
from alpha.baseline import BASELINE_DIR
from alpha.generate import GenerateError, digest
from alpha.render.ci import DEPENDABOT, JACTIONLINT, SCHEDULED, WORKFLOW
from alpha.render.tooling import BETTERLEAKS, LYCHEE, MISE, RUMDL, TYPOS
from alpha.shell import GIT_TIMEOUT

HOOKS_PATH = ".claude/alpha/githooks"
_DOCS = [
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "docs",
    ".gitignore",
]
_TOOLING = [MISE, TYPOS, RUMDL, LYCHEE, BETTERLEAKS]
_TOOLING_SUBJECT = "build: Pin the repository's check tools"
_DOCS_SUBJECT = "docs: Add product brief, principles and decisions"
_CLAUDE_SUBJECT = "chore: Add Claude Code settings and guardrails"
_CI_SUBJECT = "ci: Run every component's checks in CI"
_DEPENDABOT_SUBJECT = "ci: Schedule dependency updates"
_CLAUDE = ["CLAUDE.md", ".claude"]
UPDATE_STATE = ".claude/alpha/state/update.json"
PROPOSALS = ".claude/alpha/state/update"
_CI = ".github"
_MAX_DESCRIPTION = 50


def commit_group(path: str, component_of: Mapping[str, str]) -> str:
    if path in component_of:
        return f"build:{component_of[path]}"
    if path in (WORKFLOW, SCHEDULED, JACTIONLINT):
        return "ci"
    if path in _TOOLING:
        return "tooling"
    if path == DEPENDABOT:
        return "dependabot"
    if path == "CLAUDE.md" or path.startswith(".claude/"):
        return "chore"
    return "docs"


def _git(
    target: Path, *args: str, command: str = "commit-skeleton"
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=target,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except OSError as e:
        raise GenerateError(
            f'Cannot run git ({e}). Install git, then rerun "alpha {command} {target}".'
        ) from e
    except subprocess.TimeoutExpired:
        raise GenerateError(
            f"git {args[0]} took longer than {GIT_TIMEOUT:g}s in {target}, so alpha "
            f'stopped it. Run it yourself to see what it waits for, then rerun "alpha '
            f'{command} {target}".'
        ) from None


def status_paths(
    target: Path, *paths: str, command: str, untracked: str = "all"
) -> list[str]:
    """The paths `git status` lists, limited to `paths` when given, with
    untracked files shown as `untracked` says (normal: folders, all: every
    file)."""
    done = _git(
        target,
        "status",
        "--porcelain",
        "-z",
        f"-u{untracked}",
        "--",
        *paths,
        command=command,
    )
    if done.returncode != 0:
        raise GenerateError(
            f"git status failed in {target} ({done.stderr.strip()}), so alpha "
            "can't tell uncommitted edits from its own files. Fix that (is it a "
            f'git repository with a readable index?), then rerun "alpha {command} '
            f'{target}".'
        )
    # Unstripped: each entry starts with its status column, often a space.
    fields = done.stdout.split("\0")
    found: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if not entry:
            continue
        found.append(entry[3:])
        if entry[0] in "RC":  # a rename or copy: its source path comes next
            i += 1
    return found


def _check(target: Path, *args: str, command: str = "commit-skeleton") -> str:
    done = _git(target, *args, command=command)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip()
        raise GenerateError(
            f"git {args[0]} failed in {target}: {detail}\n"
            f'Fix that, then rerun "alpha {command} {target}".'
        )
    return done.stdout.strip()


def _check_identity(target: Path, command: str = "commit-skeleton") -> None:
    for role in ("AUTHOR", "COMMITTER"):
        done = _git(
            target,
            "-c",
            "user.useConfigOnly=true",
            "var",
            f"GIT_{role}_IDENT",
            command=command,
        )
        if done.returncode != 0:
            raise GenerateError(
                "git doesn't know who you are, so the skeleton's commits would "
                "carry a guessed author (like you@your-mac.local). Set your "
                'identity with git config --global user.name "Your Name" and '
                'git config --global user.email "you@example.com", then rerun '
                f'"alpha {command} {target}".'
            )


def _build_subject(component: dict[str, Any], scopes: list[str]) -> str:
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
    if not (target / ".git").exists():
        _check(target, "init", "-q", "-b", "main")
    _check(target, "config", "core.hooksPath", HOOKS_PATH)
    _check_identity(target)
    groups = [
        (_DOCS_SUBJECT, _DOCS),
        (_CLAUDE_SUBJECT, _CLAUDE),
        (_TOOLING_SUBJECT, _TOOLING),
    ]
    scopes = [str(s) for s in principles.get("git", {}).get("scopes", [])]
    for c in principles["components"]:
        paths = [c["path"]]
        if c["path"] == ".":
            paths.append(f":(exclude){_CI}")
        groups.append((_build_subject(c, scopes), paths))
    groups.append((_CI_SUBJECT, [WORKFLOW, SCHEDULED, JACTIONLINT]))
    groups.append((_DEPENDABOT_SUBJECT, [DEPENDABOT]))

    return _commit_groups(target, groups, trailers, "commit-skeleton")


def _commit_groups(
    target: Path,
    groups: list[tuple[str, list[str]]],
    trailers: list[str],
    command: str,
) -> list[str]:
    hashes: list[str] = []
    for subject, paths in groups:
        present = [p for p in paths if p.startswith(":(") or (target / p).exists()]
        if all(p.startswith(":(") for p in present):
            continue
        _check(target, "add", "-A", "--", *present, command=command)
        staged = _git(
            target, "diff", "--cached", "--quiet", "--", *present, command=command
        )
        if staged.returncode == 0:
            continue
        if staged.returncode != 1:
            _check(
                target, "diff", "--cached", "--quiet", "--", *present, command=command
            )
        message = subject + ("\n\n" + "\n".join(trailers) if trailers else "")
        _check(target, "commit", "-q", "-m", message, "--", *present, command=command)
        hashes.append(_check(target, "rev-parse", "HEAD", command=command))
    return hashes


def _update_subject(name: str, scopes: list[str]) -> str:
    if not scopes or name in scopes:
        return f"build({name}): Update toolchain settings"
    description = f"Update {name} toolchain settings"
    if len(description) > _MAX_DESCRIPTION:
        description = "Update toolchain settings"
    return f"build: {description}"


def _remove_proposal(target: Path, path: str) -> None:
    folder = target / PROPOSALS
    proposal = folder / path
    proposal.unlink(missing_ok=True)
    parent = proposal.parent
    while parent != folder.parent and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def commit_update(
    target: Path, principles: dict[str, Any], trailers: list[str]
) -> tuple[list[str], list[str]]:
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
    _check_identity(target, "commit-update")

    def paths_of(group: str) -> list[str]:
        return sorted(p for p, g in by_group.items() if g == group)

    scopes = [str(s) for s in principles.get("git", {}).get("scopes", [])]
    adopting = state.get("kind") == "adopt"
    # Captured or tightened baselines are alpha's writes too (spec §8b).
    baselines = [BASELINE_DIR] if (target / BASELINE_DIR).is_dir() else []
    groups: list[tuple[str, list[str]]] = [
        (
            _DOCS_SUBJECT if adopting else "docs: Update docs and decision records",
            paths_of("docs"),
        ),
        (
            _CLAUDE_SUBJECT
            if adopting
            else "chore: Update Claude Code rules and settings",
            [*paths_of("chore"), *baselines, PROJECT_JSON],
        ),
        (_TOOLING_SUBJECT, paths_of("tooling")),
    ]
    notes: list[str] = []
    for c in principles["components"]:
        if c["name"] in new_components and c["path"] == ".":
            groups.append((_build_subject(c, scopes), paths_of(f"build:{c['name']}")))
            notes.append(
                f"{c['name']} is at the project root, so only alpha's files were "
                "committed; commit any files its bootstrap made (such as "
                "lockfiles) yourself."
            )
        elif c["name"] in new_components:
            groups.append((_build_subject(c, scopes), [c["path"]]))
        else:
            groups.append(
                (_update_subject(c["name"], scopes), paths_of(f"build:{c['name']}"))
            )
    groups += [
        (_CI_SUBJECT if adopting else "ci: Update the CI checks", paths_of("ci")),
        (
            _DEPENDABOT_SUBJECT
            if adopting
            else "ci: Update the dependency update schedule",
            paths_of("dependabot"),
        ),
    ]
    hashes = _commit_groups(
        target, [g for g in groups if g[1]], trailers, "commit-update"
    )

    for path, recorded in sorted(conflicts.items()):
        file = target / path
        now = digest(file.read_bytes()) if file.is_file() else None
        unmerged = now is not None and recorded in (now, now.removeprefix("sha256:"))
        if unmerged:
            notes.append(
                f"{path}: alpha's change wasn't merged in (proposal: "
                f"{PROPOSALS}/{path})."
            )
        else:
            _remove_proposal(target, path)
    state_file.unlink()
    return hashes, notes
