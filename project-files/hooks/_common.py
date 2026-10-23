"""Shared helpers for alpha's Claude Code hooks (stdlib only).

Must parse and import on Python 3.9 (no 3.10+ syntax, no runtime `X | Y`; annotations
are lazy), so that `check_python()` can print its guard message, not a SyntaxError.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn, cast

STATE_DIR = ".claude/alpha/state"
NOT_FOUND = 127
TAIL_LINES = 60


class TimedOut(Exception):
    pass


def python_problem() -> str | None:
    """The guard message when this python3 is too old for the hooks, else None."""
    if sys.version_info >= (3, 11):  # noqa: UP036 (hooks run on whatever python3 exists)
        return None
    found = "{}.{}".format(*sys.version_info[:2])
    return (
        f"alpha needs Python 3.11+ (found {found}). Install a newer one with "
        '"brew install python" or "uv python install 3.12", then retry.'
    )


def check_python(fail_code: int = 0) -> None:
    """Exit with `fail_code` on an old python3: 0 keeps a Claude session usable,
    1 makes a git hook refuse instead of skipping its check."""
    problem = python_problem()
    if problem:
        print(problem, file=sys.stderr)
        sys.exit(fail_code)


def read_input() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError as e:
        print(
            f"alpha: hook input is not valid JSON ({e}); ignoring it. "
            "Check the hook wiring in .claude/settings.json.",
            file=sys.stderr,
        )
        return {}
    if not isinstance(data, dict):
        print("alpha: hook input is not a JSON object; ignoring it.", file=sys.stderr)
        return {}
    return data  # pyright: ignore[reportUnknownVariableType]


def project_root(inp: dict[str, Any]) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    cwd = inp.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd)
    return Path.cwd()


def load_principles(root: Path, fail_code: int = 0) -> dict[str, Any] | None:
    """The parsed principles file, or None when there is none.

    A malformed file exits with `fail_code`, as in check_python().
    """
    path = root / "docs" / "principles.toml"
    if not path.is_file():
        return None
    import tomllib  # lazy: absent on 3.9, and check_python() has exited by then

    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        print(
            f"docs/principles.toml is not valid TOML: {e}. Fix the file (it is the "
            "single source of truth for alpha's checks), or restore it with "
            '"git checkout docs/principles.toml".',
            file=sys.stderr,
        )
        sys.exit(fail_code)


def principle_applies(
    principles: dict[str, Any], principle_id: str, component: str | None = None
) -> bool:
    """Whether a principle's checks run for a component, or project-wide (None).

    Follows the principle's `active` flag and its `components` list, so dropping
    or scoping a principle in docs/principles.toml switches its checks off. An id
    the file doesn't list applies, so newer hooks keep checking older projects.
    """
    for entry in principles.get("principles", []):
        if not isinstance(entry, dict):
            continue
        p = cast("dict[str, Any]", entry)
        if p.get("id") != principle_id:
            continue
        if p.get("active", True) is False:
            return False
        names = p.get("components")
        if component is None or not isinstance(names, list):
            return True
        return component in cast("list[Any]", names)
    return True


def component_for(rel_path: str, principles: dict[str, Any]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_len = -1
    for comp in principles.get("components", []):
        base = str(comp.get("path", ".")).strip("/")
        if base in ("", "."):
            length = 0
        elif rel_path == base or rel_path.startswith(base + "/"):
            length = len(base)
        else:
            continue
        if length > best_len:
            best, best_len = comp, length
    return best


def changed_files(root: Path) -> list[str]:
    """Tracked changes vs HEAD plus untracked files, minus alpha's own state dir."""
    fix = "Make sure this is a git repository (git init) and git is installed."
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        print(f"alpha: could not run git in {root}: {e}. {fix}", file=sys.stderr)
        return []
    if proc.returncode != 0:
        print(
            f"alpha: could not list changes in {root}: {proc.stderr.strip()}. {fix}",
            file=sys.stderr,
        )
        return []
    entries = proc.stdout.split("\0")
    files: list[str] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            i += 1  # the next entry is the rename source
        if path.startswith(STATE_DIR + "/"):
            continue
        files.append(path)
    return files


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


def _globs(comp: dict[str, Any], key: str) -> list[str]:
    return [str(g) for g in comp.get(key, [])]


def is_test(rel_path: str, comp: dict[str, Any]) -> bool:
    """A test file of the component (per its test_globs, minus exclude_globs)."""
    return matches(rel_path, _globs(comp, "test_globs")) and not matches(
        rel_path, _globs(comp, "exclude_globs")
    )


def is_source(rel_path: str, comp: dict[str, Any]) -> bool:
    """A code file of the component: matches source_globs, not a test, not excluded."""
    return (
        matches(rel_path, _globs(comp, "source_globs"))
        and not matches(rel_path, _globs(comp, "test_globs"))
        and not matches(rel_path, _globs(comp, "exclude_globs"))
    )


def rel_to_root(root: Path, path: str) -> str | None:
    """POSIX path of `path` (absolute, or relative to root) under root, else None."""
    base = root.resolve()
    p = Path(path)
    try:
        return (
            (p if p.is_absolute() else base / p).resolve().relative_to(base).as_posix()
        )
    except ValueError:
        return None


def block(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(2)


def state_path(root: Path, name: str) -> Path:
    directory = root / STATE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory / name


def run_command(command: str, cwd: Path, timeout: float) -> tuple[int, str]:
    """(exit code, combined output). Raises TimedOut after `timeout` seconds."""
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except OSError as err:
        return NOT_FOUND, str(err)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        proc.communicate()
        raise TimedOut from None
    return proc.returncode, out


def tail(output: str) -> str:
    return "\n".join(output.rstrip("\n").splitlines()[-TAIL_LINES:])


def first_word(command: str) -> str:
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    return words[0] if words else command


def read_baseline(root: Path) -> str | None:
    """Commit SHA recorded as the session baseline, if any."""
    try:
        text = state_path(root, "session-base").read_text().strip()
    except OSError:
        return None
    return text or None


def write_baseline(root: Path, sha: str) -> None:
    state_path(root, "session-base").write_text(sha + "\n")


DECISIONS_DIR = "docs/decisions"
INDEX_LINES = 40
_HEADING = re.compile(r"# (\d{4})\. (.+)")


def decision_index(root: Path) -> tuple[list[tuple[int, str, str, str]], list[str]]:
    """Decision records as (number, title, status, path), and warnings for
    files in docs/decisions/ that aren't records alpha can read."""
    records: list[tuple[int, str, str, str]] = []
    warnings: list[str] = []
    folder = root / DECISIONS_DIR
    if not folder.is_dir():
        return records, warnings
    for path in sorted(folder.glob("*.md")):
        rel = f"{DECISIONS_DIR}/{path.name}"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            warnings.append(f"{rel} can't be read as UTF-8 text; fix or remove it.")
            continue
        heading = _HEADING.fullmatch(lines[0].strip()) if lines else None
        if heading is None:
            warnings.append(
                f'{rel} has no "# NNNN. Title" heading; fix it or rename it.'
            )
            continue
        status = next(
            (
                line.split(":", 1)[1].strip()
                for line in lines[1:12]
                if line.startswith("Status:")
            ),
            "",
        )
        if not status:
            warnings.append(f'{rel} has no "Status:" line; add "Status: accepted".')
            continue
        records.append((int(heading.group(1)), heading.group(2).strip(), status, rel))
    records.sort()
    return records, warnings


def _record_change(root: Path, record: str) -> str | None:
    """What a record's "Principle: id (change, scope ...)" header line says."""
    try:
        lines = (root / record).read_text(encoding="utf-8").splitlines()[:12]
    except (OSError, UnicodeDecodeError):
        return None
    for line in lines:
        found = re.fullmatch(r"Principle: \S+ \((.+)\)", line.strip())
        if found:
            return found.group(1)
    return None


def overrides_in_effect(
    principles: dict[str, Any], root: Path | None = None
) -> list[str]:
    """One line per principle the project overrode: what changed, and the record."""
    lines: list[str] = []
    for p in principles.get("principles", []):
        record = p.get("override_decision")
        if not record:
            continue
        change = _record_change(root, str(record)) if root is not None else None
        if change is None:  # no readable record: say what the principles file says
            state = "active" if p.get("active") else "inactive"
            comps = ", ".join(str(c) for c in p.get("components", [])) or "none"
            change = f"{state}, components {comps}"
        lines.append(f"{p.get('id')}: {change} ({record})")
    return lines


def context_text(root: Path, principles: dict[str, Any]) -> str:
    """What every session and subagent is told about the decisions in effect."""
    records, warnings = decision_index(root)
    if records:
        lines = [
            "alpha: decisions in effect (read the ones that bear on your change "
            "before changing anything):"
        ]
        shown = records[-INDEX_LINES:]
        lines += [
            f"- {n:04d} {title} [{status}] {path}" for n, title, status, path in shown
        ]
        if len(records) > len(shown):
            lines.append(
                f"- … {len(records) - len(shown)} older records in {DECISIONS_DIR}/"
            )
    else:
        lines = [
            f"alpha: no decision records yet in {DECISIONS_DIR}/; record decisions "
            "with the decision skill."
        ]
    overrides = overrides_in_effect(principles, root)
    if overrides:
        lines += ["Principle overrides:", *(f"- {o}" for o in overrides)]
    lines += [f"Warning: {w}" for w in warnings]
    return "\n".join(lines)


def agent_files_path(root: Path, agent_id: str) -> Path:
    """Where the files a subagent edited are listed (state/agent-<id>.json)."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", agent_id)
    return state_path(root, f"agent-{safe}.json")


def agent_files(root: Path, agent_id: str) -> list[str]:
    try:
        data = json.loads(agent_files_path(root, agent_id).read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    files: object = cast("dict[str, Any]", data).get("files")
    return [str(f) for f in cast("list[Any]", files)] if isinstance(files, list) else []


def record_agent_file(root: Path, agent_id: str, rel: str) -> None:
    files = agent_files(root, agent_id)
    if rel not in files:
        files.append(rel)
        agent_files_path(root, agent_id).write_text(json.dumps({"files": files}))


STATE_GLOB = f"{STATE_DIR}/**"


def protected_glob(rel: str, principles: dict[str, Any]) -> str | None:
    """The first protected-path glob that rel matches, if any. alpha's own
    state (and any folder holding it) is always protected: the review state
    must come from the hooks alone."""
    rel = rel.rstrip("/")
    if (
        rel == STATE_DIR
        or rel.startswith(f"{STATE_DIR}/")
        or STATE_DIR.startswith(f"{rel}/")
    ):
        return STATE_GLOB
    for glob in principles.get("protected", {}).get("paths", []):
        if matches(rel, [str(glob)]):
            return str(glob)
    return None


def protected_message(rel: str, glob: str, principles: dict[str, Any]) -> str:
    """Why a path is protected (it matched glob), and what to do instead."""
    if glob == STATE_GLOB:
        return (
            f"{rel} is protected: alpha's hooks keep their state there "
            f"({STATE_DIR}/), including the review record, and nothing else may "
            "write or delete it. Read it if you need to; ask the user if it's wrong."
        )
    head = (
        f"{rel} is protected (`{glob}` in docs/principles.toml), so Claude can't "
        "edit it."
    )
    protected = principles.get("protected", {})
    if glob in [str(g) for g in protected.get("extra", [])]:
        return f"{head} Ask the user to change it by hand."
    comp = component_for(rel, principles)
    if comp is not None and rel in [str(p) for p in comp.get("lockfiles", [])]:
        setup = comp.get("commands", {}).get("setup")
        hint = setup if isinstance(setup, str) and setup else "your package manager"
        return (
            f"{head} Lockfiles change only through the package manager (e.g. {hint})."
        )
    return f"{head} Secrets belong in the environment, never in files Claude edits."
