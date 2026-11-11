"""Run a baselined check: fail on findings the baseline doesn't hold (spec §8b).

Usage, from anywhere in the project: ratchet.py <check-id> [--file <path>]
[--capture]. The check's command and how its findings read come from its
[[baselines]] entry in docs/principles.toml; the counts per file and rule
live in .claude/alpha/baselines/<check-id>.json.

Exit 0: no new findings (fewer ones tighten the baseline, except in CI).
Exit 1: new findings, or (in CI) a baseline that could shrink.
Exit 2: the check can't be judged (no entry, no baseline, unreadable output).

Stdlib only. Parses on Python 3.9, like the hooks it runs from.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NoReturn, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import _common  # noqa: E402

BASELINES = ".claude/alpha/baselines"
TIMEOUT = 600
TAIL_LINES = 40
SHOWN = 20
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
NONE = "-"

Counts = dict[str, dict[str, int]]
Finding = tuple[str, str, str]  # file, rule, the output it came from


class Unreadable(Exception):
    pass


def baseline_path(root: Path, check: str) -> Path:
    return root / BASELINES / (check.replace(":", ".") + ".json")


def normalize_file(raw: str | None, root: Path, cwd: Path) -> str:
    """A finding's file, relative to the project root."""
    if not raw or not raw.strip():
        return NONE
    path = raw.strip()
    if path.startswith("file://"):
        path = path[len("file://") :]
    full = Path(path) if os.path.isabs(path) else cwd / path
    full = Path(os.path.normpath(str(full)))
    for base in _roots(root):
        try:
            return full.relative_to(base).as_posix()
        except ValueError:
            continue
    return path


def _roots(root: Path) -> list[Path]:
    """The root as given and resolved: on macOS /tmp is /private/tmp, and a
    tool may print either."""
    seen: list[Path] = []
    for base in (root, root.resolve()):
        if base not in seen:
            seen.append(base)
    return seen


def normalize_rule(raw: str | None, root: Path) -> str:
    """A finding's rule, without the machine's root path in it (a broken link's
    URL names the absolute file), so CI and laptops count the same rule."""
    if raw is None or not str(raw).strip():
        return NONE
    rule = str(raw).strip()
    for base in _roots(root):
        rule = rule.replace(f"{base.as_posix()}/", "")
    return rule


def parse_lines(output: str, pattern: str, root: Path, cwd: Path) -> list[Finding]:
    compiled = re.compile(pattern)
    found: list[Finding] = []
    for line in _ANSI.sub("", output).splitlines():
        match = compiled.search(line)
        if match is None:
            continue
        found.append(
            (
                normalize_file(match.group("file"), root, cwd),
                normalize_rule(match.group("rule"), root),
                line.strip(),
            )
        )
    return found


def _walk(
    node: object, steps: list[str], keys: list[str]
) -> Iterator[tuple[object, list[str]]]:
    if not steps:
        yield node, keys
        return
    step, rest = steps[0], steps[1:]
    if step == "*":
        if isinstance(node, list):
            for i, item in enumerate(cast("list[object]", node)):
                yield from _walk(item, rest, [*keys, str(i)])
        elif isinstance(node, dict):
            for key, item in cast("dict[str, object]", node).items():
                yield from _walk(item, rest, [*keys, key])
    elif isinstance(node, dict) and step in node:
        yield from _walk(cast("dict[str, object]", node)[step], rest, keys)


def _field(item: object, path: str, keys: list[str]) -> str | None:
    if not path:
        return None
    if path.startswith("@"):
        return keys[int(path[1:])]
    for value, _ in _walk(item, path.split("."), []):
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return str(value)
    return None


def parse_json(
    stdout: str, spec: dict[str, Any], root: Path, cwd: Path
) -> list[Finding]:
    try:
        data: object = json.loads(stdout)
    except ValueError as e:
        raise Unreadable(f"its output isn't JSON ({e})") from None
    where = cast("dict[str, str]", spec.get("where", {}))
    found: list[Finding] = []
    for item, keys in _walk(data, str(spec["items"]).split("."), []):
        if any(_field(item, k, keys) != v for k, v in where.items()):
            continue
        found.append(
            (
                normalize_file(_field(item, str(spec["file"]), keys), root, cwd),
                normalize_rule(_field(item, str(spec.get("rule", "")), keys), root),
                json.dumps(item, ensure_ascii=False)[:200],
            )
        )
    return found


def parse(
    entry: dict[str, Any], stdout: str, stderr: str, root: Path, cwd: Path
) -> list[Finding]:
    """The findings in a check's output: JSON from stdout alone, lines from both."""
    spec = entry.get("json")
    if isinstance(spec, dict):
        return parse_json(stdout, cast("dict[str, Any]", spec), root, cwd)
    return parse_lines(stdout + "\n" + stderr, str(entry["pattern"]), root, cwd)


def count(findings: list[Finding]) -> Counts:
    counts: Counts = {}
    for file, rule, _ in findings:
        per = counts.setdefault(file, {})
        per[rule] = per.get(rule, 0) + 1
    return counts


def compare(
    now: Counts, before: Counts, only_file: str | None = None
) -> tuple[list[tuple[str, str, int, int]], list[tuple[str, str, int, int]]]:
    """(grown, shrunk), each as (file, rule, now, baseline)."""
    grown: list[tuple[str, str, int, int]] = []
    shrunk: list[tuple[str, str, int, int]] = []
    files = set(now) | set(before)
    if only_file is not None:
        files &= {only_file}
    for file in sorted(files):
        rules = set(now.get(file, {})) | set(before.get(file, {}))
        for rule in sorted(rules):
            n = now.get(file, {}).get(rule, 0)
            b = before.get(file, {}).get(rule, 0)
            if n > b:
                grown.append((file, rule, n, b))
            elif n < b:
                shrunk.append((file, rule, n, b))
    return grown, shrunk


def tightened(now: Counts, before: Counts, only_file: str | None = None) -> Counts:
    """The baseline lowered to `now`, never raised; only `only_file` when given."""
    out: Counts = {}
    for file, rules in before.items():
        if only_file is not None and file != only_file:
            out[file] = dict(rules)
            continue
        kept = {r: min(n, now.get(file, {}).get(r, 0)) for r, n in rules.items()}
        kept = {r: n for r, n in kept.items() if n > 0}
        if kept:
            out[file] = kept
    return out


def read_baseline(path: Path) -> Counts:
    data: object = json.loads(path.read_text(encoding="utf-8"))
    raw = (
        cast("dict[str, object]", data).get("counts")
        if isinstance(data, dict)
        else None
    )
    if not isinstance(raw, dict):
        raise ValueError("it has no `counts` object")
    counts: Counts = {}
    for file, rules in cast("dict[str, object]", raw).items():
        if not isinstance(rules, dict):
            raise ValueError(f"counts[{file!r}] isn't an object")
        counts[file] = {}
        for rule, n in cast("dict[str, object]", rules).items():
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                raise ValueError(
                    f"counts[{file!r}][{rule!r}] isn't a positive whole number"
                )
            counts[file][rule] = n
    return counts


def write_baseline(path: Path, check: str, counts: Counts) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"check": check, "counts": counts}, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")


def _frozen() -> bool:
    return os.environ.get("CI", "").lower() not in ("", "0", "false")


def _tail(text: str) -> str:
    return "\n".join(text.strip().splitlines()[-TAIL_LINES:])


def _entry(principles: dict[str, Any], check: str) -> dict[str, Any] | None:
    for entry in principles.get("baselines", []):
        if not isinstance(entry, dict):
            continue
        found = cast("dict[str, Any]", entry)
        if found.get("id") == check:
            return found
    return None


def _fail(code: int, message: str) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(code)


USAGE = "Usage: ratchet.py <check-id> [--file <path>] [--capture]"


def _usage() -> tuple[str, str | None, bool]:
    args = sys.argv[1:]
    capture = "--capture" in args
    args = [a for a in args if a != "--capture"]
    file: str | None = None
    if "--file" in args:
        i = args.index("--file")
        if i + 1 >= len(args):
            _fail(2, f"ratchet.py: --file needs a path. {USAGE}")
        file = args[i + 1]
        del args[i : i + 2]
    if len(args) != 1:
        _fail(2, USAGE)
    return args[0], file, capture


def _unjudged(command: str, done: subprocess.CompletedProcess[str], why: str) -> str:
    return (
        f'"{command}" {why}, so the check can\'t be judged. Last lines:\n'
        f"{_tail(done.stdout + done.stderr)}"
    )


def main() -> None:
    _common.check_python(2)  # a check that can't run must fail, not skip
    check, file_arg, capture = _usage()
    root = _common.checkout_of(Path.cwd().resolve())
    if root is None:
        _fail(
            2,
            f"ratchet.py: {Path.cwd()} isn't in an alpha project (no "
            "docs/principles.toml next to a .git). Run it inside the project.",
        )
    principles = _common.load_principles(root, fail_code=2) or {}
    entry = _entry(principles, check)
    if entry is None:
        ids = [str(e.get("id")) for e in principles.get("baselines", [])]
        _fail(
            2,
            f"ratchet.py: {check!r} isn't a baselined check in docs/principles.toml "
            f"(baselined: {', '.join(ids) or 'none'}). Use one of those ids.",
        )
    folder = str(entry.get("dir", "."))
    cwd = root if folder in ("", ".") else root / folder
    command = str(entry["command"])
    only_file: str | None = None
    if file_arg is not None:
        template = str(entry.get("file_command", ""))
        if not template:
            _fail(
                2,
                f"ratchet.py: {check} has no file_command, so it can't check one "
                "file. Run it without --file.",
            )
        command = template.replace("{file}", shlex.quote(file_arg))
        only_file = normalize_file(file_arg, root, cwd)
    if capture and only_file is not None:
        _fail(2, "ratchet.py: --capture records the whole check; drop --file.")
    path = baseline_path(root, check)
    rel = path.relative_to(root).as_posix()
    before: Counts = {}
    if not capture:
        if not path.is_file():
            _fail(
                2,
                f"No baseline for {check} ({rel} is missing). Capture it with: "
                f"alpha baseline capture {root} --check {check}",
            )
        try:
            before = read_baseline(path)
        except (OSError, ValueError) as e:
            _fail(2, f"{rel} can't be read ({e}). Restore it: git checkout {rel}")
    try:
        done = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        _fail(
            2,
            f'"{command}" took longer than {TIMEOUT}s in {cwd}. Run it there by '
            "hand to see why.",
        )
    try:
        findings = parse(entry, done.stdout, done.stderr, root, cwd)
    except Unreadable as e:
        _fail(2, _unjudged(command, done, f"printed output that can't be read ({e})"))
    if done.returncode != 0 and not findings:
        _fail(
            2,
            _unjudged(
                command,
                done,
                f"failed (exit {done.returncode}) and none of its output reads as "
                "a finding",
            )
            + f"\nFix what it reports in {cwd}. If its output format changed, "
            f"update the {check} pattern in the recipe or registry.",
        )
    if only_file is not None:
        findings = [f for f in findings if f[0] == only_file]
    now = count(findings)
    if capture:
        write_baseline(path, check, now)
        total = sum(n for rules in now.values() for n in rules.values())
        print(f"{check}: captured {total} findings in {len(now)} files into {rel}")
        return
    grown, shrunk = compare(now, before, only_file)
    if grown:
        lines = [f"{check}: new findings the baseline ({rel}) doesn't hold:"]
        for file, rule, n, b in grown:
            lines.append(f"  {file} {rule}: {n} now, {b} in the baseline")
            shown = [text for f, r, text in findings if f == file and r == rule]
            lines += [f"    {text}" for text in shown[:SHOWN]]
        lines.append(
            "Fix the new ones (the baselined ones may stay). If a finding is "
            "wrong, record why in a decision that names the check, then run "
            f"alpha baseline capture <project> --check {check} --decision <number>."
        )
        _fail(1, "\n".join(lines))
    if not shrunk:
        return
    if _frozen():
        _fail(
            1,
            f"{check}: {len(shrunk)} baselined findings are fixed, but {rel} still "
            "holds them. Run alpha baseline tighten <project> (or this check "
            f"outside CI) and commit {rel}.",
        )
    write_baseline(path, check, tightened(now, before, only_file))
    print(f"{check}: {len(shrunk)} baselined findings are fixed. Commit {rel}.")


if __name__ == "__main__":
    main()
