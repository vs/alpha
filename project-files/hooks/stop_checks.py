"""Stop hook: blocks stopping on secrets, missing tests or docs, failing checks."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, NoReturn, cast

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402
import review  # noqa: E402

TIMEOUT = 600
BUDGET = 1100
MAX_BLOCKS = 3
MAX_SCAN_BYTES = 1_000_000
SNIFF_BYTES = 8192
DEPENDENCY_LOG = "docs/dependencies.md"
HASH_CONTENT_BYTES = 1_000_000
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


def component_name(rel: str, principles: dict[str, Any]) -> str | None:
    comp = _common.component_for(rel, principles)
    return None if comp is None else str(comp.get("name"))


def secret_problems(
    root: Path, principles: dict[str, Any], changed: list[str], base: str | None
) -> list[str]:
    problems: list[str] = []
    seen: set[tuple[str, int]] = set()
    for rel, number, text in added_lines(root, changed, base):
        if (rel, number) in seen:
            continue
        name = component_name(rel, principles)
        if not _common.principle_applies(principles, "no-secrets", name):
            continue
        if any(p.search(text) for p in SECRET_PATTERNS):
            seen.add((rel, number))
            problems.append(
                f"{rel}:{number}: looks like a secret; move it to the environment "
                "and reference it by name."
            )
    return problems


def slot_problem(command: str) -> str:
    return (
        f"waited for other agents' checks until alpha's {BUDGET}s budget ran "
        f"out; run {command} by hand"
    )


def run_step(
    command: str,
    cwd: Path,
    timeout: float | None = None,
    deadline: float | None = None,
) -> tuple[str, str]:
    """(status, output); status is ok, failed, missing, timeout or slot.

    The command takes a machine-wide slot first (see _common.heavy_slot); "slot"
    means the deadline passed while waiting for one, and nothing ran.
    """
    limit = timeout or TIMEOUT
    wait_until = deadline if deadline is not None else time.monotonic() + limit
    try:
        with _common.heavy_slot(wait_until) as got:
            if not got:
                return "slot", ""
            if deadline is not None:
                limit = max(1.0, min(limit, deadline - time.monotonic()))
            code, output = _common.run_command(command, cwd, limit)
    except _common.TimedOut:
        return "timeout", ""
    if code == _common.NOT_FOUND:
        return "missing", output
    return ("ok" if code == 0 else "failed"), output


# The principle each command run at Stop checks.
COMMAND_PRINCIPLES = {
    "typecheck": "strict-types",
    "structure": "no-dead-code",
    "test": "definition-of-done",
}


def tree_hash(root: Path, comp: dict[str, Any]) -> str | None:
    """Hash of the component's files (tracked and untracked, not ignored)."""
    base = str(comp.get("path", ".")).strip("/")
    args = ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    if base not in ("", "."):
        args += ["--", base]
    try:
        proc = subprocess.run(args, cwd=root, capture_output=True, check=False)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    excluded = [str(g) for g in comp.get("exclude_globs", [])]
    digest = hashlib.sha256()
    for rel in sorted(set(proc.stdout.decode(errors="replace").split("\0"))):
        if not rel or is_state(rel) or _common.matches(rel, excluded):
            continue
        digest.update(rel.encode() + b"\0")
        path = root / rel
        try:
            info = path.stat()
            if info.st_size <= HASH_CONTENT_BYTES:
                digest.update(hashlib.sha256(path.read_bytes()).digest())
            else:
                digest.update(f"{info.st_size}:{info.st_mtime_ns}".encode())
        except OSError:
            digest.update(b"-")  # deleted from the working tree
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return cast("dict[str, Any]", data) if isinstance(data, dict) else {}


def command_problems(
    comp: dict[str, Any], principles: dict[str, Any], root: Path, deadline: float
) -> list[str]:
    """Typecheck and test results, reused while the component's files and
    commands are unchanged since the last run."""
    commands: dict[str, Any] = comp.get("commands", {})
    name = str(comp.get("name", comp.get("path", ".")))
    steps = {
        key: command
        for key, principle in COMMAND_PRINCIPLES.items()
        if _common.principle_applies(principles, principle, name)
        and isinstance(command := commands.get(key), str)
        and command
    }
    if not steps:
        return []
    files = tree_hash(root, comp)
    key = None if files is None else json.dumps([files, steps], sort_keys=True)
    cache_path = _common.state_path(root, "stop-cache.json")
    cache = read_json(cache_path)
    hit: object = cache.get(name)
    if key is not None and isinstance(hit, dict):
        entry = cast("dict[str, Any]", hit)
        if entry.get("key") == key and isinstance(entry.get("problems"), list):
            return [str(p) for p in cast("list[Any]", entry["problems"])]
    problems, complete = run_steps(comp, steps, root, deadline)
    if key is not None and complete:
        cache[name] = {"key": key, "problems": problems}
        cache_path.write_text(json.dumps(cache))
    return problems


def run_steps(
    comp: dict[str, Any], steps: dict[str, str], root: Path, deadline: float
) -> tuple[list[str], bool]:
    """(problems, whether every step ran to completion)."""
    commands: dict[str, Any] = comp.get("commands", {})
    base = str(comp.get("path", ".")).strip("/")
    cwd = root if base in ("", ".") else root / base
    name = str(comp.get("name", base))
    problems: list[str] = []
    complete = True
    for key, command in steps.items():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            complete = False
            problems.append(
                f"{name}: {key} skipped \u2014 alpha's {BUDGET}s check budget ran "
                f"out. Run it by hand: {command}"
            )
            continue
        timeout = min(TIMEOUT, remaining)
        status, output = run_step(command, cwd, timeout, deadline)
        if status == "ok":
            continue
        if status == "slot":
            complete = False
            problems.append(f"{name}: {key} {slot_problem(command)}")
        elif status == "timeout":
            complete = False
            problems.append(
                f"{name}: {key} took longer than {int(timeout)}s ({command}). Run it "
                "by hand to see why, or tell the user."
            )
        elif status == "missing":
            complete = False  # installing the tool doesn't change the files
            setup = commands.get("setup") or "the component's setup step"
            problems.append(
                f"{_common.first_word(command)} is not installed for component "
                f"{name}. Run its setup command: {setup}"
            )
        else:
            problems.append(
                f"{name}: {key} failed ({command}):\n{_common.tail(output)}"
            )
    return problems, complete


MISSING_MISE = (
    "mise is not installed or the tool is missing. Run: mise install "
    "(install mise from https://mise.jdx.dev)"
)


def files_hash(root: Path, files: list[str]) -> str:
    """Hash of the given files' paths and contents."""
    digest = hashlib.sha256()
    for rel in sorted(files):
        digest.update(rel.encode() + b"\0")
        path = root / rel
        try:
            info = path.stat()
            if info.st_size <= HASH_CONTENT_BYTES:
                digest.update(hashlib.sha256(path.read_bytes()).digest())
            else:
                digest.update(f"{info.st_size}:{info.st_mtime_ns}".encode())
        except OSError:
            digest.update(b"-")  # deleted from the working tree
    return digest.hexdigest()


def repo_check_problems(
    root: Path, principles: dict[str, Any], changed: list[str], deadline: float
) -> list[str]:
    """Run the `stop = true` repository checks whose globs match a changed
    file, in catalog order. Results are reused while the matched files and the
    command are unchanged."""
    entries = principles.get("repo_checks")
    if not isinstance(entries, list):
        return []
    cache_path = _common.state_path(root, "stop-cache.json")
    cache = read_json(cache_path)
    dirty = False
    problems: list[str] = []
    for raw in cast("list[Any]", entries):
        if not isinstance(raw, dict):
            continue
        check = cast("dict[str, Any]", raw)
        command = check.get("command")
        if check.get("stop") is not True or not isinstance(command, str):
            continue
        check_id = str(check.get("id", command))
        globs = [str(g) for g in check.get("globs", [])]
        hit = [f for f in changed if _common.matches(f, globs)]
        if not hit:
            continue
        key = json.dumps([files_hash(root, hit), command])
        name = f"repo:{check_id}"
        cached: object = cache.get(name)
        if isinstance(cached, dict):
            entry = cast("dict[str, Any]", cached)
            if entry.get("key") == key and isinstance(entry.get("problems"), list):
                problems += [str(p) for p in cast("list[Any]", entry["problems"])]
                continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            problems.append(
                f"repo check {check_id} skipped \u2014 alpha's {BUDGET}s check "
                f"budget ran out. Run it by hand: {command}"
            )
            continue
        timeout = min(TIMEOUT, remaining)
        status, output = run_step(command, root, timeout, deadline)
        if status == "missing":  # installing the tool doesn't change the files
            problems.append(MISSING_MISE)
            break
        if status == "ok":
            found: list[str] = []
        elif status == "slot":
            found = [f"repo check {check_id}: " + slot_problem(command)]
        elif status == "timeout":
            found = [
                f"repo check {check_id} took longer than {int(timeout)}s "
                f"({command}). Run it by hand to see why, or tell the user."
            ]
        else:
            found = [
                f"repo check {check_id} failed ({command}):\n{_common.tail(output)}"
            ]
        problems += found
        if status in ("ok", "failed"):
            cache[name] = {"key": key, "problems": found}
            dirty = True
    if dirty:
        cache_path.write_text(json.dumps(cache))
    return problems


def read_count(path: Path) -> int:
    try:
        count = json.loads(path.read_text())["count"]
    except (OSError, ValueError, KeyError, TypeError):
        return 0
    return count if isinstance(count, int) else 0


def write_count(path: Path, count: int) -> None:
    path.write_text(json.dumps({"count": count}))


def existed_at(root: Path, ref: str, rel: str) -> bool:
    return git_lines(root, "cat-file", "-e", f"{ref}:{rel}") is not None


def session_start(root: Path, base: str | None) -> str | None:
    """The commit this session started from: recorded at SessionStart and kept
    for the whole session, unlike the baseline each clean Stop moves. Falls
    back to the baseline, then HEAD."""
    try:
        start = _common.state_path(root, "session-start").read_text().strip()
    except OSError:
        start = ""
    if (
        start
        and git_lines(root, "merge-base", "--is-ancestor", start, "HEAD") is not None
    ):
        return start
    return base or head_sha(root)


def migration_problems(
    root: Path, principles: dict[str, Any], base: str | None
) -> list[str]:
    """Changes to migrations that existed when the session started."""
    data = principles.get("data")
    raw = (
        cast("dict[str, Any]", data).get("migration_paths")
        if isinstance(data, dict)
        else None
    )
    globs = [str(g) for g in cast("list[Any]", raw)] if isinstance(raw, list) else []
    ref = session_start(root, base)
    if not globs or ref is None:
        return []
    # Without renames, a moved migration counts as its old path deleted.
    changed = git_lines(root, "diff", "--name-only", "--no-renames", ref) or []
    problems: list[str] = []
    for rel in changed:
        if not _common.matches(rel, globs) or not _common.principle_applies(
            principles, "safe-migrations", component_name(rel, principles)
        ):
            continue
        if existed_at(root, ref, rel):
            problems.append(
                f"{rel} existed before this session and was changed. Migrations "
                f"are append-only: put it back (git checkout {ref} -- "
                f"{shlex.quote(rel)}) and add a new migration instead. Principle "
                "safe-migrations."
            )
    return problems


def is_behavior(rel: str, principles: dict[str, Any], docs: list[str]) -> bool:
    """Whether a changed file can change public behavior: not a doc, not a test
    and not a file its component excludes from checks."""
    if _common.matches(rel, docs):
        return False
    comp = _common.component_for(rel, principles)
    if comp is None:
        return True
    excluded = [str(g) for g in comp.get("exclude_globs", [])]
    return not _common.is_test(rel, comp) and not _common.matches(rel, excluded)


def find_problems(
    root: Path,
    principles: dict[str, Any],
    changed: list[str],
    base: str | None,
    run_commands: bool = True,
) -> list[str]:
    problems: list[str] = []
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
        name = str(comp.get("name"))
        if not _common.principle_applies(principles, "tests-first-class", name):
            continue
        files = by_comp[name]
        src = [f for f in files if _common.is_source(f, comp)]
        if src and not any(_common.is_test(f, comp) for f in files):
            problems.append(
                f"{comp.get('name')}: source changed ({', '.join(src)}) but no tests "
                "changed. Principle tests-first-class: add or update tests."
            )

    if DEPENDENCY_LOG not in changed:
        for comp in components:
            name = str(comp.get("name"))
            if not _common.principle_applies(principles, "dependency-reasons", name):
                continue
            # A lockfile changes exactly when dependencies do; a manifest also
            # holds tool settings, whose edits need no log entry.
            lockfiles = [str(lock) for lock in comp.get("lockfiles", [])]
            for rel in by_comp[str(comp.get("name"))]:
                if rel in lockfiles:
                    problems.append(
                        f"Dependencies changed ({rel}) without an entry in "
                        f"{DEPENDENCY_LOG}. Record what was added and why."
                    )

    problems += migration_problems(root, principles, base)

    docs_map: dict[str, Any] = principles.get("docs_map", {})
    every_doc = [str(d) for docs in docs_map.values() for d in docs]
    for glob, docs in docs_map.items():
        doc_list = [str(d) for d in docs]
        hit = [
            f
            for f in changed
            if _common.matches(f, [glob])
            and is_behavior(f, principles, every_doc)
            and _common.principle_applies(
                principles, "docs-with-code", component_name(f, principles)
            )
        ]
        if hit and not any(_common.matches(f, doc_list) for f in changed):
            for rel in hit:
                problems.append(
                    f"{rel} changed but {', '.join(doc_list)} did not. Principle "
                    "docs-with-code: update them, or say why no doc change is needed."
                )

    if not run_commands:
        return problems
    deadline = time.monotonic() + BUDGET
    for comp in components:
        manifests = [str(m) for m in comp.get("manifests", [])]
        if any(
            _common.is_source(f, comp)
            or _common.is_test(f, comp)
            or _common.matches(f, manifests)
            for f in by_comp[str(comp.get("name"))]
        ):
            problems.extend(command_problems(comp, principles, root, deadline))
    problems += repo_check_problems(root, principles, changed, deadline)
    return problems


def flag(text: str) -> NoReturn:
    """Let Claude stop, showing the problems to the user instead of blocking."""
    print(json.dumps({"systemMessage": text}))
    print(text, file=sys.stderr)
    sys.exit(0)


def block(listing: str) -> NoReturn:
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": f"alpha checks before stopping:\n{listing}",
            }
        )
    )
    sys.exit(0)


def subagent_stop(root: Path, principles: dict[str, Any], agent: str) -> NoReturn:
    """Block a subagent only on problems with the files it edited.

    The rules run over the whole session's changes (tests or docs another
    agent wrote count), then only problems naming this subagent's files stay.
    Repository checks run on the files it edited. Type checks and tests cover
    whole components, where other agents may be mid-change, so they're left to
    the main session's Stop.
    """
    files = _common.agent_files(root, agent)
    base = session_base(root)
    changed = changed_since(root, base)
    mine = [f for f in changed if f in files] if files else []
    record = _common.agent_files_path(root, agent)
    counter = _common.state_path(root, record.stem + "-blocks")
    secrets = secret_problems(root, principles, mine, base) if mine else []
    problems = secrets
    if mine:
        found = find_problems(root, principles, changed, base, run_commands=False)
        problems = secrets + [p for p in found if any(f in p for f in mine)]
        problems += repo_check_problems(
            root, principles, mine, time.monotonic() + BUDGET
        )
    if not problems:
        record.unlink(missing_ok=True)
        counter.unlink(missing_ok=True)
        sys.exit(0)
    listing = "\n".join(f"{n}. {p}" for n, p in enumerate(problems, start=1))
    listing += (
        f"\nYou edited {', '.join(mine)}. Fix the problems in those files only; "
        "report the rest to the main session."
    )
    if not secrets:
        count = read_count(counter)
        if count >= MAX_BLOCKS:
            write_count(counter, 0)
            flag(
                "alpha: a subagent's checks still fail after 3 attempts, so it "
                "stopped; the main session's Stop still checks them before the "
                f"turn ends:\n{listing}"
            )
        write_count(counter, count + 1)
    block(listing)


def safe_gate(root: Path, principles: dict[str, Any]) -> str | None:
    """The review gate's verdict. When git can't snapshot the tree the gate
    can't judge: tell the user rather than block every stop on it."""
    try:
        return review.gate(root, principles)
    except review.SnapshotError as e:
        flag(
            f"alpha review: can't measure review debt ({e}). Fix that so the "
            "principles reviewer can run; pushes stay blocked until then."
        )


def review_block(root: Path, inp: dict[str, Any], reason: str) -> NoReturn:
    """Block on the review. The same block again within one turn means Claude
    already tried and needs the user: end the turn with a message instead of
    looping. The gate applies again at the next stop."""
    marker = _common.state_path(root, "review-blocked")
    digest = hashlib.sha256(reason.encode()).hexdigest()
    try:
        repeated = marker.read_text().strip() == digest
    except OSError:
        repeated = False
    if inp.get("stop_hook_active") and repeated:
        flag(
            f"{reason}\n\nalpha: the same review block came up twice in this turn, "
            "so Claude stopped here instead of looping. Ask Claude to carry on (run "
            "the principles-reviewer, or fix the findings), or accept a finding; the "
            "review gate applies again at the next stop."
        )
    marker.write_text(digest + "\n")
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def review_or_flag(
    root: Path, principles: dict[str, Any], inp: dict[str, Any], listing: str
) -> None:
    """Giving up on the mechanical checks never skips the review: block on it
    if it's due, naming the checks still open too. Returns when it isn't."""
    verdict = safe_gate(root, principles)
    if verdict:
        review_block(
            root, inp, f"{verdict}\n\nThese checks are still failing too:\n{listing}"
        )


def main() -> None:
    _common.check_python()
    inp = _common.read_input()
    root = _common.project_root(inp)
    principles = _common.load_principles(root)
    if principles is None:
        sys.exit(0)
    if inp.get("hook_event_name") == "SubagentStop":
        agent = inp.get("agent_id")
        if not isinstance(agent, str) or not agent:
            sys.exit(0)
        subagent_stop(root, principles, agent)
    if not inp.get("stop_hook_active"):
        # A new turn: an earlier turn's review block doesn't count as repeated.
        _common.state_path(root, "review-blocked").unlink(missing_ok=True)
    review.note_turn_end(root)  # what Claude leaves, if this Stop ends the turn
    base = session_base(root)
    changed = changed_since(root, base)
    counter = _common.state_path(root, "stop-blocks")
    secrets = secret_problems(root, principles, changed, base) if changed else []
    problems = secrets + (
        find_problems(root, principles, changed, base) if changed else []
    )
    accepted = _common.state_path(root, "stop-accepted")
    if not problems:
        write_count(counter, 0)
        accepted.unlink(missing_ok=True)
        head = head_sha(root)
        if head is not None:
            _common.write_baseline(root, head)
        # Review only work that passes the mechanical checks. Findings block
        # until fixed or accepted by the user, so this never gives up.
        verdict = safe_gate(root, principles)
        if verdict:
            review_block(root, inp, verdict)
        _common.state_path(root, "review-blocked").unlink(missing_ok=True)
        sys.exit(0)
    listing = "\n".join(f"{n}. {p}" for n, p in enumerate(problems, start=1))
    if secrets:  # never given up on, unlike the other checks
        block(listing)
    fingerprint = hashlib.sha256(listing.encode()).hexdigest()
    try:
        given_up = accepted.read_text().strip() == fingerprint
    except OSError:
        given_up = False
    if given_up:
        review_or_flag(root, principles, inp, listing)
        flag(
            "alpha: still open; the user was told after 3 attempts, so alpha won't "
            f"block on these again until they change:\n{listing}"
        )
    count = read_count(counter)
    if count >= MAX_BLOCKS:
        write_count(counter, 0)
        accepted.write_text(fingerprint + "\n")
        review_or_flag(root, principles, inp, listing)
        flag(
            "alpha: checks still failing after 3 attempts; stopping so the user can "
            f"decide:\n{listing}"
        )
    write_count(counter, count + 1)
    block(listing)


if __name__ == "__main__":
    main()
