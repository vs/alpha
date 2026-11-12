"""How a check's findings read, so a baseline can count them (spec §8b)."""

import functools
import importlib.util
import os
import posixpath
import re
import subprocess
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from alpha.shell import Ran, run_command

# The component steps a baseline may hold. format_check is fixed once (plan
# step P1), and setup isn't a check of the code.
BASELINE_STEPS = ("lint", "typecheck", "structure", "test")
RATCHET_TIMEOUT = 1800.0  # seconds: a check that runs longer is stuck
NOT_BASELINED = {
    "setup": "setup installs the toolchain; it isn't a check of the code",
    "format_check": "formatting is fixed once, in one commit, instead of baselined",
}
# Repository checks whose tool can name each finding's file and rule (the
# registry pin's `baseline`), by the check id the answers use.
REPO_BASELINED = ("actions", "typos", "markdown", "links", "agent-config")
REPO_NOT_BASELINED = {
    "secrets": "a secret is rotated, or a false positive goes in .betterleaksignore",
    "vulns": "a known vulnerability gets an osv-scanner.toml exception with a "
    "reason and a review date",
    "links-online": "it runs on the schedule only; baseline `links` instead",
    "migrations": "it checks only a pull request's own changes",
    "squawk": "it checks only a pull request's own migrations",
    "shortcuts": "a shortcut: comment is fixed by naming when to upgrade it",
    "review-dates": "a lapsed suppression is reviewed, not baselined",
    "toolchain": "an outdated tool is upgraded, not baselined",
    "baselines": "it is the check that keeps baselines from growing",
}
# Where projects keep the ratchet and the baselines.
RATCHET_SCRIPT = ".claude/alpha/checks/ratchet.py"
BASELINE_DIR = ".claude/alpha/baselines"
BASELINE_GLOB = f"{BASELINE_DIR}/**"
_KEYS = frozenset({"command", "pattern", "json", "file_command"})
_JSON_KEYS = frozenset({"items", "file", "rule", "where"})
_GROUPS = ("file", "rule")

Fail = Callable[[str, str, str], Exception]


@dataclass(frozen=True)
class JsonFindings:
    """Findings in a JSON document. `items` is a dotted path where `*` walks a
    list's items or an object's values; `file` and `rule` are dotted paths in
    an item, or `@N` for the key the N-th `*` walked; `where` keeps the items
    whose field has that value."""

    items: str
    file: str
    rule: str = ""
    where: Mapping[str, str] = field(default_factory=lambda: {})


@dataclass(frozen=True)
class Baseline:
    """A command whose output names each finding's file and rule. Exactly one
    of `pattern` (a regex with `file` and `rule` groups, matched per line) and
    `json` reads it. `file_command` checks one file, with `{file}` in it."""

    command: str
    pattern: str = ""
    json: JsonFindings | None = None
    file_command: str = ""

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {"command": self.command}
        if self.pattern:
            out["pattern"] = self.pattern
        if self.json is not None:
            j: dict[str, Any] = {"items": self.json.items, "file": self.json.file}
            if self.json.rule:
                j["rule"] = self.json.rule
            if self.json.where:
                j["where"] = dict(self.json.where)
            out["json"] = j
        if self.file_command:
            out["file_command"] = self.file_command
        return out


def _text(d: Mapping[str, object], key: str, where: str, fail: Fail) -> str:
    value = d.get(key, "")
    if not isinstance(value, str):
        raise fail(f"{where}.{key}", "must be text", "Write it as a string")
    if "\n" in value or "\r" in value:
        raise fail(f"{where}.{key}", "has a line break", "Write it on one line")
    return value


def _pattern(value: str, where: str, fail: Fail) -> str:
    try:
        compiled = re.compile(value)
    except re.error as e:
        raise fail(
            where, f"isn't a valid regular expression ({e})", "Fix the expression"
        ) from None
    missing = [g for g in _GROUPS if g not in compiled.groupindex]
    if missing:
        raise fail(
            where,
            f"has no {' or '.join(f'(?P<{g}>…)' for g in missing)} group",
            "Name the file and the rule with (?P<file>…) and (?P<rule>…); make a "
            "group optional with (…)? when some findings lack it",
        )
    return value


def _json(value: object, where: str, fail: Fail) -> JsonFindings:
    if not isinstance(value, dict):
        raise fail(
            where,
            "must be an object",
            'Write e.g. {"items": "diagnostics.*", "file": "file", "rule": "rule"}',
        )
    d = cast("dict[str, object]", value)
    extra = sorted(str(k) for k in d if k not in _JSON_KEYS)
    if extra:
        raise fail(
            where,
            f"unknown key {', '.join(extra)}",
            f"Use only: {', '.join(sorted(_JSON_KEYS))}",
        )
    items = _text(d, "items", where, fail)
    path = _text(d, "file", where, fail)
    if not items or not path:
        raise fail(
            where,
            "needs `items` and `file`",
            "Name where the findings are and where each one names its file, e.g. "
            '"items": "diagnostics.*", "file": "file"',
        )
    stars = items.split(".").count("*")
    for key in ("file", "rule"):
        ref = _text(d, key, where, fail)
        if ref.startswith("@") and not (ref[1:].isdigit() and int(ref[1:]) < stars):
            raise fail(
                f"{where}.{key}",
                f"{ref!r} doesn't name one of the {stars} `*` steps in `items`",
                "Use @0 for the key the first `*` walks, @1 for the second",
            )
    raw_where: object = d.get("where", {})
    if not isinstance(raw_where, dict) or not all(
        isinstance(k, str) and isinstance(v, str)
        for k, v in cast("dict[object, object]", raw_where).items()
    ):
        raise fail(
            f"{where}.where",
            "must map field paths to text",
            'Write e.g. {"severity": "error"}',
        )
    return JsonFindings(
        items=items,
        file=path,
        rule=_text(d, "rule", where, fail),
        where=dict(cast("dict[str, str]", raw_where)),
    )


def ratchet_command(check: str, folder: str = ".") -> str:
    """The command that runs `check` through the ratchet from `folder` (a
    component's path, relative to the project root)."""
    up = posixpath.relpath(".", folder) if folder not in ("", ".") else ""
    return f"python3 {posixpath.join(up, RATCHET_SCRIPT)} {check}"


def baseline_from_data(
    value: object, where: str, fail: Fail, *, file_slot: bool = False
) -> Baseline:
    """`file_slot`: the step also checks single files (lint_file), so the
    baseline needs a `file_command`."""
    if not isinstance(value, dict):
        raise fail(
            where,
            "must be an object",
            'Write {"command": "…", "pattern": "(?P<file>…)…(?P<rule>…)"}',
        )
    d = cast("dict[str, object]", value)
    extra = sorted(str(k) for k in d if k not in _KEYS)
    if extra:
        raise fail(
            where,
            f"unknown key {', '.join(extra)}",
            f"Use only: {', '.join(sorted(_KEYS))}",
        )
    command = _text(d, "command", where, fail)
    if not command.strip():
        raise fail(
            f"{where}.command",
            "is missing",
            "Give the check's command with machine-readable output",
        )
    pattern = _text(d, "pattern", where, fail)
    has_json = "json" in d
    if bool(pattern) == has_json:
        raise fail(
            where,
            "needs exactly one of `pattern` and `json`",
            "Read line output with a `pattern`, or JSON output with `json`",
        )
    file_command = _text(d, "file_command", where, fail)
    if file_slot and not file_command:
        raise fail(
            f"{where}.file_command",
            "is missing",
            "The step also checks one file at a time after each edit: give that "
            "command with {file} where the file goes",
        )
    if file_command and "{file}" not in file_command:
        raise fail(
            f"{where}.file_command",
            "doesn't say where the file goes",
            "Put {file} in it",
        )
    if file_command and not file_slot:
        raise fail(
            f"{where}.file_command",
            "is set, but this check never runs on one file",
            "Remove it",
        )
    return Baseline(
        command=command,
        pattern=_pattern(pattern, f"{where}.pattern", fail) if pattern else "",
        json=_json(d["json"], f"{where}.json", fail) if has_json else None,
        file_command=file_command,
    )


RATCHET = Path(__file__).resolve().parents[2] / "project-files/checks/ratchet.py"


@functools.cache
def ratchet() -> ModuleType:
    """The ratchet projects get, so the kit reads findings the same way."""
    spec = importlib.util.spec_from_file_location("alpha_ratchet", RATCHET)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def findings(
    baseline: Baseline, stdout: str, stderr: str, root: Path, cwd: Path
) -> list[tuple[str, str, str]]:
    """(file, rule, the output it came from) for each finding; raises
    ValueError when the output can't be read."""
    module = ratchet()
    try:
        found = module.parse(baseline.to_data(), stdout, stderr, root, cwd)
    except module.Unreadable as e:
        raise ValueError(str(e)) from None
    return cast("list[tuple[str, str, str]]", found)


# --- a project's baselines: show, capture, tighten ---


class BaselineError(Exception):
    """A baseline command that can't go on; the message says what to do."""


def baseline_file(target: Path, check: str) -> Path:
    return target / BASELINE_DIR / (check.replace(":", ".") + ".json")


def baselined(target: Path) -> list[str]:
    """The ids docs/principles.toml lists under [[baselines]], in order."""
    path = target / "docs" / "principles.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise BaselineError(
            f"{path} can't be read ({e}). Run this in a project alpha generated or "
            "adopted, or restore the file with git checkout docs/principles.toml."
        ) from None
    entries = cast("list[object]", data.get("baselines", []))
    return [
        str(cast("dict[str, object]", e)["id"])
        for e in entries
        if isinstance(e, dict) and "id" in e
    ]


def _known(target: Path, check: str) -> list[str]:
    ids = baselined(target)
    if check not in ids:
        raise BaselineError(
            f"{check!r} isn't baselined in {target}/docs/principles.toml "
            f"(baselined: {', '.join(ids) or 'none'}). Add it to adoption.baselines "
            "in the answers and run alpha update, or use one of those ids."
        )
    return ids


def counts(target: Path, check: str) -> dict[str, dict[str, int]] | None:
    """The check's baseline, or None when it isn't captured."""
    path = baseline_file(target, check)
    if not path.is_file():
        return None
    try:
        return cast("dict[str, dict[str, int]]", ratchet().read_baseline(path))
    except (OSError, ValueError) as e:
        rel = path.relative_to(target).as_posix()
        raise BaselineError(
            f"{rel} can't be read ({e}). Restore it: git checkout {rel}"
        ) from None


def show(target: Path) -> list[dict[str, Any]]:
    """Per check: its id, whether it's captured, its total, files and rules."""
    out: list[dict[str, Any]] = []
    for check in baselined(target):
        found = counts(target, check)
        rules: dict[str, int] = {}
        for per in (found or {}).values():
            for rule, n in per.items():
                rules[rule] = rules.get(rule, 0) + n
        out.append(
            {
                "check": check,
                "captured": found is not None,
                "total": sum(rules.values()),
                "files": len(found or {}),
                "rules": dict(sorted(rules.items(), key=lambda kv: (-kv[1], kv[0]))),
            }
        )
    return out


def describe(rows: list[dict[str, Any]], target: Path) -> str:
    if not rows:
        return "No baselines: every check fails on any finding."
    lines: list[str] = []
    for row in rows:
        if not row["captured"]:
            lines.append(
                f"{row['check']}: not captured. Run alpha baseline capture {target} "
                f"--check {row['check']}"
            )
            continue
        top = ", ".join(f"{r} {n}" for r, n in list(row["rules"].items())[:5])
        lines.append(
            f"{row['check']}: {row['total']} findings in {row['files']} files"
            + (f" ({top})" if top else "")
        )
    return "\n".join(lines)


def _run_ratchet(target: Path, *args: str, frozen: bool = False) -> Ran:
    script = target / RATCHET_SCRIPT
    if not script.is_file():
        raise BaselineError(
            f"{script} is missing. Restore it with git checkout {RATCHET_SCRIPT}."
        )
    env = {k: v for k, v in os.environ.items() if k != "CI"}
    if frozen:
        env["CI"] = "true"
    done = run_command(
        ["python3", str(script), *args], target, RATCHET_TIMEOUT, merge=False, env=env
    )
    if done is None:
        raise BaselineError(
            f"ratchet.py {' '.join(args)} took longer than {RATCHET_TIMEOUT:g}s, so "
            "alpha stopped it. Run the check it names yourself to see why it's "
            "slow, fix that, then retry."
        )
    return done


def find_record(target: Path, number: str) -> Path | None:
    """docs/decisions/<number>-*.md, if there is one."""
    if not number.isdigit():
        return None
    found = sorted((target / "docs" / "decisions").glob(f"{int(number):04d}-*.md"))
    return found[0] if found else None


def accepts(record: Path, token: str) -> bool:
    """Whether the record is accepted and names `token` in backticks."""
    try:
        text = record.read_text(encoding="utf-8")
    except OSError:
        return False
    lines = [line.strip() for line in text.splitlines()]
    return "Status: accepted" in lines and f"`{token}`" in text


def _decision(target: Path, number: str, check: str) -> Path:
    record = find_record(target, number)
    if record is None:
        raise BaselineError(
            f"No decision record {number} in docs/decisions/. Record the decision "
            "first (the project's /decision skill), then pass its number."
        )
    rel = record.relative_to(target).as_posix()
    if not accepts(record, check):
        raise BaselineError(
            f"{rel} doesn't accept a larger {check} baseline: it needs "
            f"`Status: accepted` and the check id in backticks (`{check}`), with "
            "why the new findings stay."
        )
    if named_before_branch(target, rel, check):
        raise BaselineError(
            f"{rel} already named `{check}` before this branch, so it accepted an "
            "earlier growth, not this one. The pull request check counts only a "
            "decision that names the check for the first time on the branch: "
            "record a new one for these findings."
        )
    return record


def _branch_point(target: Path) -> str | None:
    """Where HEAD left the default branch (origin's, else main or master)."""
    for ref in ("origin/HEAD", "main", "master"):
        done = subprocess.run(
            ["git", "merge-base", ref, "HEAD"],
            cwd=target,
            capture_output=True,
            text=True,
        )
        if done.returncode == 0:
            return done.stdout.strip()
    return None


def named_before_branch(target: Path, rel: str, token: str) -> bool:
    """Whether the record at `rel` already named `token` where the branch
    started: the pull request check accepts only a record that names it here
    first."""
    point = _branch_point(target)
    if point is None:
        return False
    shown = subprocess.run(
        ["git", "show", f"{point}:{rel}"], cwd=target, capture_output=True, text=True
    )
    return shown.returncode == 0 and f"`{token}`" in shown.stdout


def capture(target: Path, check: str, decision: str | None = None) -> str:
    """Record the check's findings as its baseline. A baseline that already
    exists may only grow with an accepted decision naming the check."""
    _known(target, check)
    before = counts(target, check)
    path = baseline_file(target, check)
    old = path.read_bytes() if path.is_file() else None
    done = _run_ratchet(target, check, "--capture")
    if done.code != 0:
        raise BaselineError(done.err.strip() or done.out.strip())
    now = counts(target, check) or {}
    grown, _ = ratchet().compare(now, before or {})
    if before is not None and grown:
        if decision is None:
            assert old is not None
            path.write_bytes(old)
            lines = [f"  {f} {r}: {n} now, {b} in the baseline" for f, r, n, b in grown]
            raise BaselineError(
                f"Capturing {check} would grow its baseline:\n"
                + "\n".join(lines)
                + "\nFix those findings, or record why they stay in a decision "
                f"naming `{check}` and rerun with --decision <number>."
            )
        try:
            _decision(target, decision, check)
        except BaselineError:
            assert old is not None
            path.write_bytes(old)
            raise
    return done.out.strip()


def capture_missing(target: Path) -> list[str]:
    """Capture every listed check that has no baseline yet."""
    return [
        capture(target, check)
        for check in baselined(target)
        if not baseline_file(target, check).is_file()
    ]


def tighten(target: Path) -> tuple[list[str], list[str]]:
    """Run every baselined check locally: (tightened files, failures)."""
    changed: list[str] = []
    problems: list[str] = []
    for check in baselined(target):
        path = baseline_file(target, check)
        old = path.read_bytes() if path.is_file() else None
        done = _run_ratchet(target, check)
        if done.code != 0:
            problems.append(done.err.strip() or done.out.strip())
        elif path.is_file() and path.read_bytes() != old:
            changed.append(path.relative_to(target).as_posix())
    return changed, problems
