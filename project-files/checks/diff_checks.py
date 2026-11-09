"""Checks on a pull request's diff against its base (run in CI by mise).

Usage, from the repo root: diff_checks.py immutable-migrations|squawk
Stdlib only. ALPHA_BASE is the base ref (empty outside pull requests) and
PR_BODY the pull request description.
"""

import fnmatch
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

APPROVAL = "alpha: migration edit approved"


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
    return [str(g) for g in value] if isinstance(value, list) else []  # type: ignore[reportUnknownVariableType]


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def resolve_base(check: str) -> str | None:
    base = os.environ.get("ALPHA_BASE", "").strip()
    if (
        base
        and git("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode
        == 0
    ):
        return base
    print(f"alpha: no base ref (not a pull request); {check} skipped")
    return None


def changes(base: str) -> list[tuple[str, str]]:
    out = git("diff", "--name-status", "--no-renames", f"{base}...HEAD").stdout
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        status, _, path = line.partition("\t")
        if path:
            rows.append((status[:1], path))
    return rows


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
        print(f"  Restore it: git checkout {base} -- {path}")
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


def main(argv: list[str]) -> int:
    checks = {"immutable-migrations": immutable_migrations, "squawk": squawk}
    if len(argv) != 2 or argv[1] not in checks:
        print(f"usage: {Path(argv[0]).name} immutable-migrations|squawk")
        return 2
    return checks[argv[1]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
