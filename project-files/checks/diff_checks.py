"""Checks on a pull request's diff against its base (run in CI by mise).

Usage, from the repo root: diff_checks.py immutable-migrations|squawk|baselines
Stdlib only. ALPHA_BASE is the base ref (empty outside pull requests) and
PR_BODY the pull request description.
"""

import fnmatch
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, cast

APPROVAL = "alpha: migration edit approved"
BASELINES = ".claude/alpha/baselines"
DECISIONS = "docs/decisions/"


def _match_parts(path: list[str], pat: list[str]) -> bool:
    if not pat:
        return not path
    if pat[0] == "**":
        return any(_match_parts(path[k:], pat[1:]) for k in range(len(path) + 1))
    if not path:
        return False
    return fnmatch.fnmatchcase(path[0], pat[0]) and _match_parts(path[1:], pat[1:])


def matches(rel_path: str, globs: list[str]) -> bool:
    parts = rel_path.split("/")
    return any(_match_parts(parts, g.split("/")) for g in globs)


def data_globs(key: str) -> list[str]:
    try:
        with open("docs/principles.toml", "rb") as f:
            data = tomllib.load(f).get("data", {})
    except (OSError, tomllib.TOMLDecodeError):
        return []
    value = data.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(g) for g in cast(list[Any], value)]


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def resolve_base(check: str) -> str | None:
    base = os.environ.get("ALPHA_BASE", "").strip()
    if not base:
        print(f"alpha: no base ref (not a pull request); {check} skipped")
        return None
    if git("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode == 0:
        return base
    print(
        f"alpha: base {base} didn't resolve; fetch the full history "
        f"(actions/checkout with fetch-depth: 0). {check} skipped"
    )
    return None


class GitError(Exception):
    pass


def changes(base: str) -> list[tuple[str, str]]:
    result = git("diff", "--name-status", "--no-renames", "-z", f"{base}...HEAD")
    if result.returncode != 0:
        raise GitError(
            f"alpha: git diff {base}...HEAD failed:\n{result.stderr.strip()}\n"
            "  Fetch the full history: actions/checkout with fetch-depth: 0, "
            f"and make sure {base} shares history with this branch."
        )
    fields = result.stdout.split("\0")
    return [(fields[i][:1], fields[i + 1]) for i in range(0, len(fields) - 1, 2)]


def immutable_migrations() -> int:
    base = resolve_base("immutable-migrations")
    if base is None:
        return 0
    globs = data_globs("migration_paths")
    edited = [p for s, p in changes(base) if s in ("M", "D", "T") and matches(p, globs)]
    if not edited:
        return 0
    body_lines = [ln.strip() for ln in os.environ.get("PR_BODY", "").splitlines()]
    if APPROVAL in body_lines:
        print(
            f"alpha: migration edit approved in the PR description: {', '.join(edited)}"
        )
        return 0
    for path in edited:
        print(f"alpha: {path} is an applied migration, changed or deleted vs {base}.")
        print(f"  Restore it: git checkout {base} -- {shlex.quote(path)}")
        print("  Then put the change in a new migration instead.")
    print(f"  If the edit is intended, add a line `{APPROVAL}` to the PR description.")
    return 1


def squawk() -> int:
    base = resolve_base("squawk")
    if base is None:
        return 0
    globs = data_globs("squawk_paths")
    files = [
        p
        for s, p in changes(base)
        if s == "A" and p.endswith(".sql") and matches(p, globs)
    ]
    if not files:
        return 0
    if shutil.which("squawk") is None:
        print("alpha: squawk is not installed; run: mise install")
        return 1
    return subprocess.run(["squawk", *files]).returncode


def _ratchet() -> Any:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ratchet  # the same reading of a baseline file as the checks

    return ratchet


def _counts_at(base: str, path: str) -> dict[str, dict[str, int]]:
    shown = git("show", f"{base}:{path}")
    return _ratchet().parse_baseline(shown.stdout) if shown.returncode == 0 else {}


def _accepting(base: str) -> list[tuple[str, str]]:
    """(path, text) of each accepted decision record the pull request adds."""
    out: list[tuple[str, str]] = []
    for status, path in changes(base):
        if status != "A" or not path.startswith(DECISIONS) or not path.endswith(".md"):
            continue
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        lines = [ln.strip() for ln in text.splitlines()]
        if "Status: accepted" in lines:
            out.append((path, text))
    return out


def baselines() -> int:
    base = resolve_base("baselines")
    if base is None:
        return 0
    ratchet = _ratchet()
    folder = Path(BASELINES)
    paths = {p.as_posix() for p in folder.glob("*.json")}
    listed = git("ls-tree", "--name-only", f"{base}", f"{BASELINES}/")
    paths |= {p for p in listed.stdout.splitlines() if p.endswith(".json")}
    records = _accepting(base)
    failed = False
    for path in sorted(paths):
        now_path = Path(path)
        try:
            now: dict[str, dict[str, int]] = (
                ratchet.read_baseline(now_path) if now_path.is_file() else {}
            )
            before = _counts_at(base, path)
        except ValueError as e:
            print(f"alpha: {path} can't be read ({e}). Restore it from {base}.")
            failed = True
            continue
        grown, _ = ratchet.compare(now, before)
        if not grown:
            continue
        check = now_path.stem.replace(".", ":")
        named = f"`{check}`"
        if any(named in text for _, text in records):
            print(f"alpha: {path} grows, accepted by a decision naming {named}.")
            continue
        failed = True
        print(f"alpha: {path} grows against {base}; baselines only shrink:")
        for file, rule, n, b in grown:
            print(f"  {file} {rule}: {n} findings, {b} before")
        print(
            f"  Fix the new findings, or, if they're right to keep, add a decision "
            f"record under {DECISIONS} (Status: accepted) that names {named} and "
            "says why, in this pull request."
        )
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    checks = {
        "immutable-migrations": immutable_migrations,
        "squawk": squawk,
        "baselines": baselines,
    }
    if len(argv) != 2 or argv[1] not in checks:
        print(f"usage: {Path(argv[0]).name} {'|'.join(checks)}")
        return 2
    try:
        return checks[argv[1]]()
    except GitError as err:
        print(err)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
