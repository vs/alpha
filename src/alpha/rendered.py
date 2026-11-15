"""alpha's last render of a project, kept in git objects that follow its history.

`alpha apply` writes the render as a tree object. `alpha commit` makes it a
commit, chained under `refs/alpha/rendered` so every render stays reachable,
and adds a note under `refs/notes/alpha-rendered` to its own last commit,
naming that render. The next update finds its base by walking HEAD's history
for the first commit with such a note, so a discarded update, another branch
or another worktree never hides a change. Nothing here is committed to the
project's files; the refs and notes stay local, and another clone has none.
"""

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from alpha.generate import GenerateError
from alpha.shell import GIT_TIMEOUT

RENDERED_REF = "refs/alpha/rendered"
NOTES_REF = "alpha-rendered"
_IDENTITY = {
    "GIT_AUTHOR_NAME": "alpha",
    "GIT_AUTHOR_EMAIL": "alpha@localhost",
    "GIT_COMMITTER_NAME": "alpha",
    "GIT_COMMITTER_EMAIL": "alpha@localhost",
}


def _git(
    target: Path,
    *args: str,
    stdin: str | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=target,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            env={**os.environ, **(env or {})},
        )
    except OSError as e:
        raise GenerateError(f"Cannot run git ({e}). Install git, then retry.") from e
    except subprocess.TimeoutExpired:
        raise GenerateError(
            f"git {args[0]} took longer than {GIT_TIMEOUT:g}s in {target}, so alpha "
            "stopped it. Run it yourself to see what it waits for, then retry."
        ) from None


def _must(
    target: Path,
    *args: str,
    stdin: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    done = _git(target, *args, stdin=stdin, env=env)
    if done.returncode != 0:
        raise GenerateError(
            f"git {args[0]} failed in {target}: {done.stderr.strip()}. Fix that, "
            "then retry."
        )
    return done.stdout


def write_tree(target: Path, texts: Mapping[str, str], executable: set[str]) -> str:
    """Store the render as a tree object; returns its id."""
    rows: list[str] = []
    for path in sorted(texts):
        blob = _must(target, "hash-object", "-w", "--stdin", stdin=texts[path])
        mode = "100755" if path in executable else "100644"
        rows.append(f"{mode} {blob.strip()}\t{path}")
    git_dir = Path(_must(target, "rev-parse", "--absolute-git-dir").strip())
    index = git_dir / "alpha-render-index"
    env = {"GIT_INDEX_FILE": str(index)}
    try:
        _must(target, "read-tree", "--empty", env=env)
        _must(
            target,
            "update-index",
            "--index-info",
            stdin="\n".join(rows) + "\n",
            env=env,
        )
        return _must(target, "write-tree", env=env).strip()
    finally:
        index.unlink(missing_ok=True)


def record(target: Path, tree: str) -> str:
    """Make `tree` alpha's latest render: a commit under RENDERED_REF, named
    by a note on HEAD. Returns the render commit."""
    parent = _git(target, "rev-parse", "--verify", "-q", RENDERED_REF).stdout.strip()
    args = ["commit-tree", tree, "-m", "alpha render"]
    if parent:
        args += ["-p", parent]
    commit = _must(target, *args, env=_IDENTITY).strip()
    _must(target, "update-ref", RENDERED_REF, commit)
    _must(
        target,
        "notes",
        f"--ref={NOTES_REF}",
        "add",
        "-f",
        "-m",
        commit,
        "HEAD",
        env=_IDENTITY,
    )
    _keep_through_rewrites(target)
    return commit


def _keep_through_rewrites(target: Path) -> None:
    """Have git copy the render note when a rebase or an amend rewrites the
    commit it's on (notes.rewrite.* default to true for listed refs)."""
    listed = _git(target, "config", "--get-all", "notes.rewriteRef").stdout.split()
    if f"refs/notes/{NOTES_REF}" not in listed:
        _must(target, "config", "--add", "notes.rewriteRef", f"refs/notes/{NOTES_REF}")


@dataclass(frozen=True)
class Base:
    commit: str
    texts: dict[str, str]


def find_base(target: Path) -> Base | None:
    """The render the latest commit in HEAD's history with a render note names,
    or None (a new project, or a clone that never ran alpha)."""
    listed = _git(target, "notes", f"--ref={NOTES_REF}", "list")
    if listed.returncode != 0 or not listed.stdout.strip():
        return None
    noted = {
        parts[1]: parts[0]
        for parts in (line.split() for line in listed.stdout.splitlines())
        if len(parts) == 2
    }
    history = _git(target, "rev-list", "--topo-order", "HEAD")
    if history.returncode != 0:
        return None
    for commit in history.stdout.split():
        if commit not in noted:
            continue
        render = _must(target, "cat-file", "blob", noted[commit]).strip()
        if _git(target, "cat-file", "-e", f"{render}^{{tree}}").returncode != 0:
            return None  # the render was pruned; behave as a fresh clone
        return Base(render, _read_tree(target, render))
    return None


def _read_tree(target: Path, commit: str) -> dict[str, str]:
    listing = _must(target, "ls-tree", "-r", "-z", commit)
    entries: list[tuple[str, str]] = []
    for row in listing.split("\0"):
        meta, _, path = row.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            entries.append((path, parts[2]))
    texts: dict[str, str] = {}
    for path, blob in entries:
        texts[path] = _must(target, "cat-file", "blob", blob)
    return texts


def forget(target: Path) -> None:
    """Drop alpha's renders and their notes (purge)."""
    _git(target, "update-ref", "-d", RENDERED_REF)
    _git(target, "update-ref", "-d", f"refs/notes/{NOTES_REF}")
