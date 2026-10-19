"""Stop hook: blocks stopping on secrets, missing tests or docs, failing checks."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402

TIMEOUT = 600
BUDGET = 1100
MAX_BLOCKS = 3
MAX_SCAN_BYTES = 1_000_000
SNIFF_BYTES = 8192
DEPENDENCY_LOG = "docs/dependencies.md"
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"xox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(
        r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"
    ),
]
HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def git_lines(root: Path, *args: str) -> list[str] | None:
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=root,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError:
        return None
    return proc.stdout.splitlines() if proc.returncode == 0 else None


def is_scannable(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size > MAX_SCAN_BYTES:
            return False
        with path.open("rb") as f:
            return b"\0" not in f.read(SNIFF_BYTES)
    except OSError:
        return False


def whole_file_lines(root: Path, rel: str) -> list[tuple[str, int, str]]:
    path = root / rel
    if not is_scannable(path):
        return []
    text = path.read_text(errors="replace")
    return [(rel, n, line) for n, line in enumerate(text.splitlines(), start=1)]


def is_state(rel: str) -> bool:
    return rel.startswith(_common.STATE_DIR + "/")


def session_base(root: Path) -> str | None:
    """The recorded baseline, if it is still an ancestor of HEAD."""
    base = _common.read_baseline(root)
    if base is None:
        return None
    try:
        proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, "HEAD"],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    return base if proc.returncode == 0 else None


def head_sha(root: Path) -> str | None:
    lines = git_lines(root, "rev-parse", "--verify", "-q", "HEAD")
    return lines[0] if lines else None


def changed_since(root: Path, base: str | None) -> list[str]:
    if base is None:
        return _common.changed_files(root)
    names = git_lines(root, "diff", "--name-only", base) or []
    names += git_lines(root, "ls-files", "--others", "--exclude-standard") or []
    return [n for n in dict.fromkeys(names) if not is_state(n)]


def parse_added(diff: list[str]) -> list[tuple[str, int, str]]:
    """Added lines of a -U0 diff; hunks are consumed by their header counts."""
    found: list[tuple[str, int, str]] = []
    current: str | None = None
    old_left = new_left = number = 0
    for line in diff:
        if old_left > 0 or new_left > 0:  # inside a hunk: content, never a header
            if line.startswith("+"):
                if current is not None:
                    found.append((current, number, line[1:]))
                number += 1
                new_left -= 1
            elif line.startswith("-"):
                old_left -= 1
            elif line.startswith(" "):
                old_left -= 1
                new_left -= 1
                number += 1
            continue
        if line.startswith("diff --git "):
            current = None
        elif line.startswith("+++ "):
            name = line[4:].split("\t")[0]
            current = name[2:] if name.startswith("b/") else None
            if current is not None and is_state(current):
                current = None
        elif line.startswith("@@"):
            m = HUNK.match(line)
            if m:
                old_left = int(m.group(1) or 1)
                number = int(m.group(2))
                new_left = int(m.group(3) or 1)
    return found


def added_lines(
    root: Path, changed: list[str], base: str | None
) -> list[tuple[str, int, str]]:
    """(file, line number in the new file, text) for every line added since base."""
    if head_sha(root) is None:
        found: list[tuple[str, int, str]] = []
        for rel in changed:
            found.extend(whole_file_lines(root, rel))
        return found
    diff = git_lines(root, "diff", base or "HEAD", "-U0", "--no-color", "--no-ext-diff")
    found = parse_added(diff or [])
    for rel in git_lines(root, "ls-files", "--others", "--exclude-standard") or []:
        if not is_state(rel):
            found.extend(whole_file_lines(root, rel))
    return found


def secret_problems(root: Path, changed: list[str], base: str | None) -> list[str]:
    problems: list[str] = []
    seen: set[tuple[str, int]] = set()
    for rel, number, text in added_lines(root, changed, base):
        if (rel, number) in seen:
            continue
        if any(p.search(text) for p in SECRET_PATTERNS):
            seen.add((rel, number))
            problems.append(
                f"{rel}:{number}: looks like a secret; move it to the environment "
                "and reference it by name."
            )
    return problems


def run_step(command: str, cwd: Path, timeout: float | None = None) -> tuple[str, str]:
    """(status, output); status is ok, failed, missing or timeout."""
    try:
        code, output = _common.run_command(command, cwd, timeout or TIMEOUT)
    except _common.TimedOut:
        return "timeout", ""
    if code == _common.NOT_FOUND:
        return "missing", output
    return ("ok" if code == 0 else "failed"), output


def command_problems(comp: dict[str, Any], root: Path, deadline: float) -> list[str]:
    commands: dict[str, Any] = comp.get("commands", {})
    base = str(comp.get("path", ".")).strip("/")
    cwd = root if base in ("", ".") else root / base
    name = str(comp.get("name", base))
    problems: list[str] = []
    for key in ("typecheck", "test"):
        command = commands.get(key)
        if not isinstance(command, str) or not command:
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            problems.append(
                f"{name}: {key} skipped \u2014 alpha's {BUDGET}s check budget ran "
                f"out. Run it by hand: {command}"
            )
            continue
        timeout = min(TIMEOUT, remaining)
        status, output = run_step(command, cwd, timeout)
        if status == "ok":
            continue
        if status == "timeout":
            problems.append(
                f"{name}: {key} took longer than {int(timeout)}s ({command}). Run it "
                "by hand to see why, or tell the user."
            )
        elif status == "missing":
            setup = commands.get("setup") or "the component's setup step"
            problems.append(
                f"{_common.first_word(command)} is not installed for component "
                f"{name}. Run its setup command: {setup}"
            )
        else:
            problems.append(
                f"{name}: {key} failed ({command}):\n{_common.tail(output)}"
            )
    return problems


def read_count(path: Path) -> int:
    try:
        count = json.loads(path.read_text())["count"]
    except (OSError, ValueError, KeyError, TypeError):
        return 0
    return count if isinstance(count, int) else 0


def write_count(path: Path, count: int) -> None:
    path.write_text(json.dumps({"count": count}))


def find_problems(
    root: Path, principles: dict[str, Any], changed: list[str], base: str | None
) -> list[str]:
    problems = secret_problems(root, changed, base)
    components: list[dict[str, Any]] = []
    by_comp: dict[str, list[str]] = {}
    for rel in changed:
        comp = _common.component_for(rel, principles)
        if comp is None:
            continue
        key = str(comp.get("name"))
        if key not in by_comp:
            components.append(comp)
        by_comp.setdefault(key, []).append(rel)

    for comp in components:
        files = by_comp[str(comp.get("name"))]
        src = [
            f for f in files if _common.matches(f, list(comp.get("source_globs", [])))
        ]
        tests = list(comp.get("test_globs", []))
        if src and not any(_common.matches(f, tests) for f in files):
            problems.append(
                f"{comp.get('name')}: source changed ({', '.join(src)}) but no tests "
                "changed. Principle tests-first-class: add or update tests."
            )

    if DEPENDENCY_LOG not in changed:
        for comp in components:
            manifests = list(comp.get("manifests", []))
            for rel in by_comp[str(comp.get("name"))]:
                if rel in manifests:
                    problems.append(
                        f"Dependency manifest changed ({rel}) without an entry in "
                        f"{DEPENDENCY_LOG}. Record what was added and why."
                    )

    docs_map: dict[str, Any] = principles.get("docs_map", {})
    for glob, docs in docs_map.items():
        doc_list = [str(d) for d in docs]
        hit = [f for f in changed if _common.matches(f, [glob])]
        if hit and not any(d in changed for d in doc_list):
            for rel in hit:
                problems.append(
                    f"{rel} changed but {', '.join(doc_list)} did not. Principle "
                    "docs-with-code: update them, or say why no doc change is needed."
                )

    deadline = time.monotonic() + BUDGET
    for comp in components:
        relevant = (
            list(comp.get("source_globs", []))
            + list(comp.get("test_globs", []))
            + list(comp.get("manifests", []))
        )
        if any(_common.matches(f, relevant) for f in by_comp[str(comp.get("name"))]):
            problems.extend(command_problems(comp, root, deadline))
    return problems


def main() -> None:
    _common.check_python()
    inp = _common.read_input()
    root = _common.project_root(inp)
    principles = _common.load_principles(root)
    if principles is None:
        sys.exit(0)
    base = session_base(root)
    changed = changed_since(root, base)
    counter = _common.state_path(root, "stop-blocks")
    problems = find_problems(root, principles, changed, base) if changed else []
    if not problems:
        write_count(counter, 0)
        head = head_sha(root)
        if head is not None:
            _common.write_baseline(root, head)
        sys.exit(0)
    listing = "\n".join(f"{n}. {p}" for n, p in enumerate(problems, start=1))
    count = read_count(counter)
    if count >= MAX_BLOCKS:
        write_count(counter, 0)
        text = (
            "alpha: checks still failing after 3 attempts; stopping so the user can "
            f"decide:\n{listing}"
        )
        print(json.dumps({"systemMessage": text}))
        print(text, file=sys.stderr)
        sys.exit(0)
    write_count(counter, count + 1)
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": f"alpha checks before stopping:\n{listing}",
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
