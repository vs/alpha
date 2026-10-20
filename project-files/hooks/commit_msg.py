"""Git commit-msg hook: enforces conventional commits (not a Claude Code hook)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402

DEFAULT_TYPES = [
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "test",
    "build",
    "chore",
    "perf",
    "ci",
    "revert",
]
EXAMPLE = 'Example: "feat(api): Add token refresh"'
PASS_PREFIXES = ("Merge ", 'Revert "', "fixup! ", "squash! ", "amend! ")
SCISSORS = "# ------------------------ >8 ------------------------"
HEADER = re.compile(r"^(?P<type>[a-z]+)(\((?P<scope>[a-z0-9-]+)\))?!?: (?P<desc>.+)$")
TRAILER = re.compile(r"^[A-Za-z-]+: ")
MAX_DESC = 50
MAX_BODY = 72
NOT_IMPERATIVE = {
    "adds",
    "fixes",
    "updates",
    "removes",
    "changes",
    "makes",
    "uses",
    "moves",
    "renames",
}
IMPERATIVE_EXCEPTIONS = {
    "embed",
    "seed",
    "feed",
    "need",
    "shed",
    "speed",
    "bring",
    "ring",
    "string",
    "sing",
    "ping",
}


def fail(rule: str) -> None:
    print(f"commit-msg: {rule}. {EXAMPLE}", file=sys.stderr)
    sys.exit(1)


def toplevel() -> Path:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return Path.cwd()
    out = proc.stdout.strip()
    return Path(out) if proc.returncode == 0 and out else Path.cwd()


def clean(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith(SCISSORS):
            break
        if line.startswith("#"):
            continue
        lines.append(line.rstrip())
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def is_imperative(word: str) -> bool:
    low = word.lower()
    if low in IMPERATIVE_EXCEPTIONS:
        return True
    return not (low in NOT_IMPERATIVE or low.endswith(("ed", "ing")))


def check(lines: list[str], types: list[str], scopes: list[str] | None) -> None:
    if not lines:
        fail("the message is empty; write a header like type(scope): Description")
    header = lines[0]
    if header.startswith(PASS_PREFIXES):
        return
    m = HEADER.match(header)
    if m is None:
        fail(
            f'the header "{header}" does not match type(scope): Description '
            "(lowercase type, optional scope in parentheses, a colon and a space)"
        )
        return
    kind, scope, desc = m.group("type"), m.group("scope"), m.group("desc")
    if kind not in types:
        fail(f'unknown type "{kind}"; use one of: {", ".join(types)}')
    if scope is not None and scopes and scope not in scopes:
        fail(f'unknown scope "{scope}"; use one of: {", ".join(scopes)}')
    if len(desc) > MAX_DESC:
        fail(f"the description is {len(desc)} chars; keep it to {MAX_DESC} or fewer")
    if not desc[0].isupper():
        fail("the description must start with a capital letter")
    if desc.endswith("."):
        fail("the description must not end with a period")
    word = desc.split()[0]
    if not is_imperative(word):
        fail(f'"{word}" is not imperative; write "Add", not "Adds", "Added", "Adding"')
    if len(lines) > 1:
        if lines[1]:
            fail("a blank line must separate the header from the body")
        for line in lines[2:]:
            if len(line) > MAX_BODY and "://" not in line and not TRAILER.match(line):
                fail(f"body lines wrap at {MAX_BODY} chars; rewrap: {line[:30]}...")


def main() -> None:
    _common.check_python()
    if len(sys.argv) != 2:
        print(
            "commit-msg: expected the commit message file as the only argument. "
            "Run this through git (git config core.hooksPath .claude/alpha/githooks).",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        text = Path(sys.argv[1]).read_text(errors="replace")
    except OSError as e:
        print(
            f"commit-msg: cannot read the message file ({e}). Retry the commit.",
            file=sys.stderr,
        )
        sys.exit(1)
    principles = _common.load_principles(toplevel())
    types, scopes = DEFAULT_TYPES, None
    if principles is not None:
        if not _common.principle_applies(principles, "clean-history"):
            sys.exit(0)
        git = principles.get("git", {})
        types = [str(t) for t in git.get("types", DEFAULT_TYPES)]
        scopes = [str(s) for s in git.get("scopes", [])]
    check(clean(text), types, scopes)


if __name__ == "__main__":
    main()
