"""Notes that a source change needs no test, or no doc change (alpha's spec,
R12.6).

The Stop check asks for a test with every source change, and for the mapped
docs with every change to a documented path. A rename, a constant or wiring
needs no test; an internal change needs no doc update. Claude says why here,
and the note holds while the file keeps the content it had when noted. The
principles-reviewer checks each reason.

Usage, from the project root: untested.py [--docs] "<why>" <path> ...
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).parent))
import _common

NOTES = "untested.json"
GIT_TIMEOUT = 30
USAGE = (
    'Run it as: python3 .claude/alpha/hooks/untested.py [--docs] "<why>" <path> '
    "..., from the root of an alpha project (--docs: no doc change needed)."
)


def _path(root: Path) -> Path:
    return _common.state_path(root, NOTES)


def _blob(root: Path, rel: str) -> str:
    """The file's content as git names it; "deleted" when it's gone, and
    "unknown" when git can't say, which matches no note."""
    if not (root / rel).is_file():
        return "deleted"
    try:
        proc = subprocess.run(
            ["git", "hash-object", "--", rel],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _notes(root: Path) -> list[dict[str, Any]]:
    try:
        data: object = json.loads(_path(root).read_text())
    except (OSError, ValueError):
        return []
    items = cast("list[object]", data) if isinstance(data, list) else []
    return [cast("dict[str, Any]", n) for n in items if isinstance(n, dict)]


def note(root: Path, reason: str, paths: list[str], kind: str = "test") -> list[str]:
    """Record why these changes need no test (`kind` "test") or no doc change
    ("docs"); returns the paths that aren't in the project."""
    rels = [_common.rel_to_root(root, str(Path.cwd() / p)) for p in paths]
    outside = [p for p, rel in zip(paths, rels, strict=True) if rel is None]
    if outside:
        return outside
    kept = [
        n
        for n in _notes(root)
        if (n.get("path") not in rels or n.get("kind", "test") != kind)
        and _blob(root, str(n.get("path"))) == n.get("blob")
    ]
    kept += [
        {"path": rel, "kind": kind, "reason": reason, "blob": _blob(root, rel)}
        for rel in rels
        if rel is not None
    ]
    _path(root).write_text(json.dumps(kept, indent=2))
    return []


def notes(root: Path, kind: str = "test") -> dict[str, str]:
    """Paths noted as needing no test (or, with `kind` "docs", no doc change),
    while their content is the noted one."""
    found: dict[str, str] = {}
    for n in _notes(root):
        path, reason = n.get("path"), n.get("reason")
        if n.get("kind", "test") != kind:
            continue
        if isinstance(path, str) and isinstance(reason, str):
            if _blob(root, path) == n.get("blob"):
                found[path] = reason
    return found


def main() -> None:
    _common.check_python()
    root = _common.project_root({"cwd": os.getcwd()})
    args = sys.argv[1:]
    kind = "docs" if args[:1] == ["--docs"] else "test"
    args = args[1:] if kind == "docs" else args
    if len(args) < 2 or _common.checkout_of(root.resolve()) is None:
        print(USAGE, file=sys.stderr)
        sys.exit(1)
    if len(args[0].split()) < 2:
        print(
            'untested.py: give the reason in a few words, e.g. "renames the field '
            'only", before the paths.',
            file=sys.stderr,
        )
        sys.exit(1)
    outside = note(root, args[0], args[1:], kind)
    if outside:
        print(
            f"untested.py: {', '.join(outside)} isn't in this project; name files "
            "from its root.",
            file=sys.stderr,
        )
        sys.exit(1)
    print("noted: the principles-reviewer checks the reason")


if __name__ == "__main__":
    main()
