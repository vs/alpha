"""Adopting an existing repo (spec §5b): the survey of what's already there."""

import json
import posixpath
import re
import subprocess
from pathlib import Path
from typing import Any, cast

from alpha.answers import PROJECT_JSON
from alpha.defaults import Source, load_defaults, load_survey
from alpha.recipes import RecipeBook, matches

CAP = 50  # entries per list; the rest are counted
SUBJECTS = 50  # recent commits checked against the convention
HOOK_MANAGERS = "hook_managers"


class AdoptError(Exception):
    """The repo can't be adopted as it is; the message says what to do."""


def _git(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args], cwd=target, capture_output=True, text=True
        )
    except OSError as e:
        raise AdoptError(f"Cannot run git ({e}). Install git, then retry.") from e


def _out(target: Path, *args: str) -> str | None:
    done = _git(target, *args)
    return done.stdout.strip() if done.returncode == 0 else None


def _refuse_alpha(target: Path) -> None:
    path = target / PROJECT_JSON
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(data, dict) and "manifest" in data:
        raise AdoptError(
            f"alpha already generated or adopted {target} ({PROJECT_JSON} has a "
            "manifest). Change it with /alpha:extend instead."
        )


def _repo(target: Path) -> None:
    top = _out(target, "rev-parse", "--show-toplevel")
    if top is None:
        raise AdoptError(
            f"{target} isn't a git repository. alpha adopts a repo's committed "
            "code: run git init, commit the code, then retry."
        )
    if Path(top).resolve() != target.resolve():
        raise AdoptError(
            f"{target} is inside the repository at {top}. Adopt the repository "
            f"from its root: run this on {top}."
        )
    if _out(target, "rev-parse", "--verify", "--quiet", "HEAD") is None:
        raise AdoptError(
            f"{target} has no commits yet. Commit the code first, then retry."
        )


def _capped(items: list[str], key: str, into: dict[str, Any]) -> None:
    into[key] = items[:CAP]
    if len(items) > CAP:
        into[f"{key}_more"] = len(items) - CAP


def _default_branch(target: Path, branch: str) -> str:
    origin = _out(target, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    if origin:
        return origin.removeprefix("refs/remotes/origin/")
    for name in ("main", "master"):
        if _out(target, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
            return name
    return branch


def _dirty(target: Path) -> list[str]:
    # Unstripped: each entry starts with its status column, often a space.
    fields = _git(target, "status", "--porcelain", "-z", "-unormal").stdout.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if not entry:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":  # a rename or copy: its source path comes next
            i += 1
    return paths


def _conventional(target: Path, types: list[str]) -> dict[str, Any]:
    log = _out(target, "log", f"-{SUBJECTS}", "--format=%s") or ""
    subjects = [s for s in log.splitlines() if s]
    pattern = re.compile(rf"^({'|'.join(map(re.escape, types))})(\([^)]+\))?!?: \S")
    others = [s for s in subjects if not pattern.match(s)]
    return {
        "checked": len(subjects),
        "matching": len(subjects) - len(others),
        "others": others[:5],
    }


def _git_facts(target: Path, defaults: dict[str, Any]) -> dict[str, Any]:
    branch = _out(target, "rev-parse", "--abbrev-ref", "HEAD") or ""
    dirty = _dirty(target)
    facts: dict[str, Any] = {
        "head": _out(target, "rev-parse", "HEAD") or "",
        "branch": branch,
        "default_branch": _default_branch(target, branch),
        "clean": not dirty,
    }
    _capped(sorted(dirty), "dirty", facts)
    facts["commits"] = int(_out(target, "rev-list", "--count", "HEAD") or "0")
    facts["conventional"] = _conventional(target, list(defaults["git"]["types"]))
    facts["hooks_path"] = _out(target, "config", "--get", "core.hooksPath") or ""
    return facts


def _tracked(target: Path) -> list[str]:
    done = _git(target, "ls-files", "-z")
    if done.returncode != 0:
        raise AdoptError(f"git ls-files failed in {target}: {done.stderr.strip()}")
    return sorted(p for p in done.stdout.split("\0") if p)


def _inside(path: str, folder: str) -> str | None:
    """`path` relative to `folder`, or None when it's outside."""
    if folder == ".":
        return path
    return path[len(folder) + 1 :] if path.startswith(f"{folder}/") else None


def _components(files: list[str], book: RecipeBook) -> list[dict[str, Any]]:
    stacks = sorted({*book.kit_stacks(), *book.drafted})
    found: dict[tuple[str, str], list[str]] = {}
    for stack in stacks:
        markers = set(book.get(stack).detect)
        for path in files:
            if posixpath.basename(path) in markers:
                folder = posixpath.dirname(path) or "."
                found.setdefault((folder, stack), []).append(path)
    folders = {folder for folder, _ in found}
    out: list[dict[str, Any]] = []
    for (folder, stack), marked in sorted(found.items()):
        recipe = book.get(stack)
        nested = [f for f in folders if f != folder and _inside(f, folder)]
        sources = tests = 0
        for path in files:
            rel = _inside(path, folder)
            if rel is None or any(_inside(path, n) is not None for n in nested):
                continue
            if matches(rel, recipe.exclude_globs):
                continue
            if matches(rel, recipe.test_globs):
                tests += 1
            elif matches(rel, recipe.source_globs):
                sources += 1
        out.append(
            {
                "path": folder,
                "stack": stack,
                "markers": sorted(marked),
                "sources": sources,
                "tests": tests,
            }
        )
    return out


def survey(
    target: Path, source: Source, book: RecipeBook | None = None
) -> dict[str, Any]:
    """What the repo already has, in facts (spec §5b, step 1)."""
    _refuse_alpha(target)
    _repo(target)
    files = _tracked(target)
    globs = load_survey(source)
    git = _git_facts(target, load_defaults(source))
    managers = [p for p in files if matches(p, globs.get(HOOK_MANAGERS, []))]
    _capped(managers, HOOK_MANAGERS, git)
    listed: dict[str, Any] = {}
    for key, patterns in globs.items():
        if key != HOOK_MANAGERS:
            _capped([p for p in files if matches(p, patterns)], key, listed)
    return {
        "git": git,
        "components": _components(files, book or RecipeBook()),
        "files": listed,
        "tracked": len(files),
    }


def saved_adoption(target: Path) -> dict[str, Any]:
    """The `adoption` object project.json holds now, or an empty one."""
    try:
        data: object = json.loads((target / PROJECT_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    adoption: object = cast(dict[str, Any], data).get("adoption", {})
    return cast(dict[str, Any], adoption) if isinstance(adoption, dict) else {}
