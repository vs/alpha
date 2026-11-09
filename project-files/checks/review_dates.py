"""Fail when a security suppression has no review date or its date passed.

Usage, from the repo root: review_dates.py [--today YYYY-MM-DD]
Stdlib only. Reads osv-scanner.toml and .betterleaksignore; a missing file
passes. Prints one `file:line: problem. fix` per problem and exits 1.
"""

import argparse
import re
import sys
import tomllib
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

OSV = "osv-scanner.toml"
BETTERLEAKS = ".betterleaksignore"
# Betterleaks stops honoring an entry that has a trailing comment, so the
# reason and date go on the line above it.
BL_FORM = "# <reason, 2+ words> (review YYYY-MM-DD)"
REVIEW = re.compile(r"^#\s*(?P<reason>.*?)\s*\(review (?P<date>[^)]*)\)\s*$")
HEADER = re.compile(r"^\s*\[\[\s*(\"IgnoredVulns\"|IgnoredVulns)\s*\]\]\s*(#.*)?$")
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_date(text: str) -> date | None:
    """A real date written exactly as YYYY-MM-DD, else None."""
    if not ISO.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def date_problem(text: str, today: date) -> str | None:
    d = parse_date(text)
    if d is None:
        return f"{text!r} is not a real date (write YYYY-MM-DD)"
    if d < today:
        return f"review date passed ({d.isoformat()})"
    return None


def read_utf8(path: Path) -> str | None:
    """File text, or None after printing a not-UTF-8 problem."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        print(f"{path}: not valid UTF-8. Fix: save it as UTF-8")
        return None


def words(reason: str) -> int:
    return len(reason.split())


def check_osv(today: date) -> list[str]:
    path = Path(OSV)
    if not path.is_file():
        return []
    text = read_utf8(path)
    if text is None:
        return [f"{OSV}: unreadable"]
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        found: list[str] = []
        for n, line in enumerate(text.splitlines(), 1):
            m = re.match(r"\s*ignoreUntil\s*=\s*(\d{4}-\d+-\d+)", line)
            if m and parse_date(m.group(1)) is None:
                found.append(
                    f"{OSV}:{n}: ignoreUntil is not a real date; write "
                    "YYYY-MM-DD. Fix: set a real date, for example "
                    "ignoreUntil = 2026-12-31, or remove the [[IgnoredVulns]] "
                    "entry"
                )
        if found:
            return found
        at = re.search(r"line (\d+)", str(e))
        if at:
            loc = f"{OSV}:{at.group(1)}"
        elif "end of document" in str(e):
            loc = f"{OSV}:{max(len(text.splitlines()), 1)}"
        else:
            loc = OSV
        return [
            f"{loc}: not valid TOML ({e}). Fix: correct the syntax, or remove "
            "the suppression"
        ]
    headers = [n for n, line in enumerate(text.splitlines(), 1) if HEADER.match(line)]
    raw_entries: Any = data.get("IgnoredVulns", [])
    if not isinstance(raw_entries, list):
        return [
            f"{OSV}: IgnoredVulns must be an array of tables. Fix: write each "
            "suppression as [[IgnoredVulns]], or remove it"
        ]
    entries = cast(list[Any], raw_entries)
    aligned = len(headers) == len(entries)
    problems: list[str] = []
    for i, raw in enumerate(entries):
        entry = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        vid = entry.get("id", "?")
        where = f"{OSV}:{headers[i]}" if aligned else f"{OSV}: entry {i + 1}"
        fix = (
            "Fix: set ignoreUntil to a new real date and a reason of at least "
            "two words, or remove the suppression"
        )
        until: Any = entry.get("ignoreUntil")
        if until is None:
            problems.append(f"{where}: {vid} has no ignoreUntil. {fix}")
        else:
            if isinstance(until, datetime):
                until_text = until.date().isoformat()
            elif isinstance(until, date):
                until_text = until.isoformat()
            else:
                until_text = str(until)
            bad = date_problem(until_text, today)
            if bad:
                problems.append(f"{where}: {vid} ignoreUntil: {bad}. {fix}")
        reason: Any = entry.get("reason")
        if not isinstance(reason, str) or words(reason) < 2:
            problems.append(
                f"{where}: {vid} needs a reason of at least two words. {fix}"
            )
    return problems


def check_betterleaks(today: date) -> list[str]:
    path = Path(BETTERLEAKS)
    if not path.is_file():
        return []
    text = read_utf8(path)
    if text is None:
        return [f"{BETTERLEAKS}: unreadable"]
    lines = text.splitlines()
    problems: list[str] = []
    for n, line in enumerate(lines, 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        where = f"{BETTERLEAKS}:{n}"
        fix = (
            f"Fix: put `{BL_FORM}` on the line above the entry, or remove "
            "the suppression"
        )
        if re.search(r"[ \t]#", entry):
            problems.append(
                f"{where}: a trailing comment stops betterleaks honoring "
                f"the entry. Move the reason and date to the line above. {fix}"
            )
            continue
        above = lines[n - 2].strip() if n >= 2 else ""
        m = REVIEW.match(above)
        if m is None:
            problems.append(
                f"{where}: {entry} has no review comment on the line above. {fix}"
            )
            continue
        bad = date_problem(m.group("date"), today)
        if bad:
            problems.append(f"{where}: {bad}. {fix}")
        if words(m.group("reason")) < 2:
            problems.append(f"{where}: the reason needs at least two words. {fix}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    today = date.today()
    if args.today:
        parsed = parse_date(args.today)
        if parsed is None:
            print(
                f"--today {args.today!r} is not a real date (write YYYY-MM-DD)",
                file=sys.stderr,
            )
            return 1
        today = parsed
    problems = check_osv(today) + check_betterleaks(today)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
