"""Stop hook: blocks stopping on secrets, missing tests or docs, failing checks."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402

TIMEOUT = 600
MAX_BLOCKS = 3
MAX_SCAN_BYTES = 1_000_000
SNIFF_BYTES = 8192
DEPENDENCY_LOG = "docs/dependencies.md"
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"xox[abpr]-[A-Za-z0-9-]{10,}"),
    re.compile(
        r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"
    ),
]
HUNK = re.compile(r"^@@ -\S+ \+(\d+)")


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


def added_lines(root: Path, changed: list[str]) -> list[tuple[str, int, str]]:
    """(file, line number in the new file, text) for every line added since HEAD."""
    has_head = git_lines(root, "rev-parse", "--verify", "-q", "HEAD") is not None
    if not has_head:
        found: list[tuple[str, int, str]] = []
        for rel in changed:
            found.extend(whole_file_lines(root, rel))
        return found
    found = []
    diff = git_lines(root, "diff", "HEAD", "-U0", "--no-color", "--no-ext-diff")
    current: str | None = None
    number = 0
    for line in diff or []:
        if line.startswith("+++ "):
            name = line[4:].split("\t")[0]
            current = name[2:] if name.startswith("b/") else None
            if current is not None and current.startswith(_common.STATE_DIR + "/"):
                current = None
        elif line.startswith("@@"):
            m = HUNK.match(line)
            number = int(m.group(1)) if m else 0
        elif current is not None and line.startswith("+"):
            found.append((current, number, line[1:]))
            number += 1
    untracked = git_lines(root, "ls-files", "--others", "--exclude-standard") or []
    for rel in untracked:
        if not rel.startswith(_common.STATE_DIR + "/"):
            found.extend(whole_file_lines(root, rel))
    return found


def secret_problems(root: Path, changed: list[str]) -> list[str]:
    problems: list[str] = []
    seen: set[tuple[str, int]] = set()
    for rel, number, text in added_lines(root, changed):
        if (rel, number) in seen:
            continue
        if any(p.search(text) for p in SECRET_PATTERNS):
            seen.add((rel, number))
            problems.append(
                f"{rel}:{number}: looks like a secret; move it to the environment "
                "and reference it by name."
            )
    return problems


def run_step(command: str, cwd: Path) -> tuple[str, str]:
    """(status, output); status is ok, failed, missing or timeout."""
    try:
        code, output = _common.run_command(command, cwd, TIMEOUT)
    except _common.TimedOut:
        return "timeout", ""
    if code == _common.NOT_FOUND:
        return "missing", output
    return ("ok" if code == 0 else "failed"), output


def command_problems(comp: dict[str, Any], root: Path) -> list[str]:
    commands: dict[str, Any] = comp.get("commands", {})
    base = str(comp.get("path", ".")).strip("/")
    cwd = root if base in ("", ".") else root / base
    name = str(comp.get("name", base))
    problems: list[str] = []
    for key in ("typecheck", "test"):
        command = commands.get(key)
        if not isinstance(command, str) or not command:
            continue
        status, output = run_step(command, cwd)
        if status == "ok":
            continue
        if status == "timeout":
            problems.append(
                f"{name}: {key} took longer than {TIMEOUT}s ({command}). Run it by "
                "hand to see why, or tell the user."
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
    root: Path, principles: dict[str, Any], changed: list[str]
) -> list[str]:
    problems = secret_problems(root, changed)
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

    for comp in components:
        problems.extend(command_problems(comp, root))
    return problems


def main() -> None:
    _common.check_python()
    inp = _common.read_input()
    root = _common.project_root(inp)
    principles = _common.load_principles(root)
    if principles is None:
        sys.exit(0)
    changed = _common.changed_files(root)
    counter = _common.state_path(root, "stop-blocks")
    problems = find_problems(root, principles, changed) if changed else []
    if not problems:
        write_count(counter, 0)
        sys.exit(0)
    listing = "\n".join(f"{n}. {p}" for n, p in enumerate(problems, start=1))
    count = read_count(counter)
    if count >= MAX_BLOCKS:
        write_count(counter, 0)
        print(
            "alpha: checks still failing after 3 attempts; stopping so the user can "
            f"decide:\n{listing}",
            file=sys.stderr,
        )
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
