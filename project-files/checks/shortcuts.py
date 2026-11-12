"""Fail when a `shortcut:` comment names no upgrade trigger; list them all.

Usage, from the repo root: shortcuts.py [--list]
A deliberate shortcut is marked `shortcut: <the limit>, <when to upgrade>`.
Stdlib only. Reads every text file git would track, except alpha's own under
.claude/alpha/. Prints one `file:line: problem. Fix: ...` per problem and exits
1; with --list, prints the ledger and exits 0.
"""

import re
import subprocess
import sys
from pathlib import Path

COMMENT = re.compile(r"#|//|/\*|--|;|<!--")
PROSE_COMMENT = re.compile(r"<!--")
MARKER = re.compile(r"\s?shortcut:\s*(?P<text>.*?)\s*(?:\*/|-->)?$")
QUOTES = "\"'`"
# Prose has only HTML comments, and apostrophes rather than string literals.
PROSE = {".md", ".markdown", ".rst", ".html", ".htm"}
FORM = "shortcut: <the limit>, <when to upgrade>"
EXAMPLE = "shortcut: reads the whole file into memory, stream it past 100 MB"
SKIP = ".claude/alpha/"


def tracked(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        print(f"shortcuts: git ls-files failed: {out.stderr.strip()}")
        sys.exit(2)
    return sorted({p for p in out.stdout.split("\0") if p and not p.startswith(SKIP)})


def markers(root: Path) -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for rel in tracked(root):
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        prose = Path(rel).suffix.lower() in PROSE
        for n, line in enumerate(text.splitlines(), start=1):
            marked = marker(line, prose)
            if marked is not None:
                found.append((rel, n, marked))
    return found


def marker(line: str, prose: bool) -> str | None:
    """The text of the line's `shortcut:` comment, skipping string literals."""
    comment = PROSE_COMMENT if prose else COMMENT
    quote = ""
    in_comment = prose
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in QUOTES and not in_comment:
            quote = ch
        elif start := comment.match(line, i):
            found = MARKER.match(line, start.end())
            if found:
                return found.group("text")
            in_comment = True
        i += 1
    return None


def split(text: str) -> tuple[str, str] | None:
    """(limit, upgrade), or None when the comment names no upgrade trigger."""
    limit, comma, upgrade = text.partition(",")
    if not comma or not limit.strip() or len(upgrade.split()) < 2:
        return None
    return limit.strip(), upgrade.strip()


def main() -> int:
    root = Path.cwd()
    found = markers(root)
    if "--list" in sys.argv[1:]:
        missing = 0
        for rel, n, text in found:
            parts = split(text)
            if parts is None:
                missing += 1
                print(f"{rel}:{n}, {text or '(empty)'}. no-trigger")
            else:
                print(f"{rel}:{n}, limit: {parts[0]}. upgrade: {parts[1]}.")
        if found:
            print(f"{len(found)} shortcuts, {missing} with no upgrade trigger.")
        else:
            print("No shortcuts. Clean ledger.")
        return 0
    problems = [
        f"{rel}:{n}: this shortcut names no upgrade trigger. Fix: write "
        f"`{FORM}`, e.g. `{EXAMPLE}`"
        for rel, n, text in found
        if split(text) is None
    ]
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
