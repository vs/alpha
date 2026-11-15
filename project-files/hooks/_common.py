"""Shared helpers for alpha's Claude Code hooks (stdlib only).

Must parse and import on Python 3.9 (no 3.10+ syntax, no runtime `X | Y`; annotations
are lazy), so that `check_python()` can print its guard message, not a SyntaxError.
"""

from __future__ import annotations

import contextlib
import fnmatch
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple, NoReturn, cast

STATE_DIR = ".claude/alpha/state"
ALPHA_DIR = ".claude/alpha"
HOOKS_DIR = ".claude/alpha/hooks"
NOTES_DIR = ".claude/alpha/notes"
SETTINGS = ".claude/settings.json"
LOCAL_SETTINGS = ".claude/settings.local.json"
UNINSTALL = "/alpha:uninstall"
BASELINE_DIR = ".claude/alpha/baselines"  # spec §8b; only shrinks
PRINCIPLES = "docs/alpha/principles.toml"
NOT_FOUND = 127
TAIL_LINES = 60


class TimedOut(Exception):
    pass


fcntl: ModuleType | None
try:
    import fcntl
except ImportError:  # not POSIX: run heavy commands without slots
    fcntl = None

SLOT_POLL = 0.2


def _slot_files() -> list[Path] | None:
    """The machine-wide slot lock files, or None when slots can't be used."""
    try:
        count = int(os.environ.get("ALPHA_SLOTS", ""))
    except ValueError:
        count = 0
    if count < 1:
        count = max(1, (os.cpu_count() or 2) // 4)
    folder = Path.home() / ".cache" / "alpha" / "slots"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return [folder / f"{n}.lock" for n in range(count)]


@contextlib.contextmanager
def heavy_slot(deadline: float) -> Generator[bool]:
    """Hold one machine-wide slot while a heavy command runs.

    Several agents' Stop hooks otherwise start typechecks and test suites at
    once and starve each other. Yields True when a slot is held (or none is
    needed: CI, a nested call, no fcntl, no writable HOME) and False when
    `deadline` (a time.monotonic() value) passed while waiting.
    """
    if (
        fcntl is None
        or os.environ.get("CI")
        or os.environ.get("ALPHA_SLOT_HELD") == "1"
    ):
        yield True
        return
    files = _slot_files()
    if files is None:
        yield True
        return
    held: Any = None
    try:
        while held is None:
            for path in files:
                try:
                    handle = path.open("a")
                except OSError:
                    continue
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    handle.close()
                    continue
                held = handle  # assigned at once so the finally closes it
                break
            if held is None:
                if time.monotonic() >= deadline:
                    break
                time.sleep(SLOT_POLL)
        if held is None:
            yield False
            return
        previous = os.environ.get("ALPHA_SLOT_HELD")
        os.environ["ALPHA_SLOT_HELD"] = "1"  # so nested hook calls don't wait
        try:
            yield True
        finally:
            if previous is None:
                os.environ.pop("ALPHA_SLOT_HELD", None)
            else:
                os.environ["ALPHA_SLOT_HELD"] = previous
    finally:
        if held is not None:
            held.close()


def python_problem() -> str | None:
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
    return cast("dict[str, Any]", data)


def checkout_of(path: Path) -> Path | None:
    """The alpha project checkout (the main one or a worktree) holding path:
    one with alpha's hooks, even when its principles file is gone."""
    for folder in (path, *path.parents):
        if (folder / ".git").exists():
            alpha = (folder / PRINCIPLES).is_file() or (folder / HOOKS_DIR).is_dir()
            return folder if alpha else None
    return None


def project_root(inp: dict[str, Any], path: str | None = None) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    cwd = inp.get("cwd")
    here = Path(cwd) if isinstance(cwd, str) and cwd else Path(env or Path.cwd())
    starts = [here / path] if path else []
    for start in [*starts, here]:
        found = checkout_of(start.resolve())
        if found is not None:
            return found
    return Path(env) if env else here


def load_principles(root: Path, fail_code: int = 0) -> dict[str, Any] | None:
    path = root / "docs" / "alpha" / "principles.toml"
    if not path.is_file():
        return None
    import tomllib  # noqa: PLC0415 - absent on 3.9; check_python() has exited by then

    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        print(
            f"docs/alpha/principles.toml is not valid TOML: {e}. Fix the file (it is "
            "the single source of truth for alpha's checks), or restore it with "
            '"git checkout docs/alpha/principles.toml".',
            file=sys.stderr,
        )
        sys.exit(fail_code)


def principle_applies(
    principles: dict[str, Any], principle_id: str, component: str | None = None
) -> bool:
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


def components_for(rel_path: str, principles: dict[str, Any]) -> list[dict[str, Any]]:
    """The components a change to the file concerns: the one whose folder
    holds it, and each that lists it as a manifest or lockfile (the root files
    of a workspace are every member's)."""
    own = component_for(rel_path, principles)
    found = [] if own is None else [own]
    for comp in principles.get("components", []):
        shared = [*comp.get("manifests", []), *comp.get("lockfiles", [])]
        if comp is not own and rel_path in [str(p) for p in shared]:
            found.append(comp)
    return found


def changed_files(root: Path) -> list[str]:
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
    return matches(rel_path, _globs(comp, "test_globs")) and not matches(
        rel_path, _globs(comp, "exclude_globs")
    )


def is_source(rel_path: str, comp: dict[str, Any]) -> bool:
    return (
        matches(rel_path, _globs(comp, "source_globs"))
        and not matches(rel_path, _globs(comp, "test_globs"))
        and not matches(rel_path, _globs(comp, "exclude_globs"))
    )


def rel_to_root(root: Path, path: str) -> str | None:
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
    try:
        text = state_path(root, "session-base").read_text().strip()
    except OSError:
        return None
    return text or None


def write_baseline(root: Path, sha: str) -> None:
    state_path(root, "session-base").write_text(sha + "\n")


CONTRIBUTING = "CONTRIBUTING.md"
GIT_LOG_TIMEOUT = 30  # seconds: reading the branch's commit messages
_ACCEPTS = re.compile(r"^Accepts: (F-[0-9a-f]{6})\b", re.M)


class ExceptionRow(NamedTuple):
    """A row of CONTRIBUTING.md's Exceptions table: a path, a check and why the
    check doesn't hold there."""

    path: str
    check: str
    row: str


def parse_exceptions(text: str) -> list[ExceptionRow]:
    """The rows of the Exceptions table in a CONTRIBUTING.md's text."""
    found: list[ExceptionRow] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Exceptions"
        elif (
            inside and line.startswith("|") and not line.startswith(("| Path", "|---"))
        ):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2:
                found.append(ExceptionRow(cells[0], cells[1], line.strip()))
    return found


def exception_rows(root: Path) -> list[ExceptionRow]:
    try:
        return parse_exceptions((root / CONTRIBUTING).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return []


def newly_excepted(now: str, before: str, check: str) -> bool:
    """Whether the Exceptions table in `now` names `check` for a path the table
    in `before` didn't: rewording an older row's reason doesn't count."""
    old = {(e.path, e.check) for e in parse_exceptions(before)}
    return any(
        e.check == check and (e.path, e.check) not in old for e in parse_exceptions(now)
    )


def accepted_findings(root: Path) -> set[str]:
    """The review findings an `Accepts: F-xxxxxx <reason>` line settles in the
    last commits' messages, in any paragraph: only its first id counts."""
    try:
        proc = subprocess.run(
            ["git", "log", "-n", "500", "--format=%B"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=GIT_LOG_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return set(_ACCEPTS.findall(proc.stdout)) if proc.returncode == 0 else set()


def overrides_in_effect(principles: dict[str, Any]) -> list[str]:
    return [
        f"{p.get('id')}: {p['override']}"
        for p in principles.get("principles", [])
        if p.get("override")
    ]


WRITING = ("smallest-change", "scope-first", "fix-at-the-root", "lean-structure")


def writing_principles(principles: dict[str, Any]) -> list[str]:
    """The code-writing principles in effect, to steer code as it's written,
    not only at review."""
    found: list[str] = []
    for entry in principles.get("principles", []):
        if not isinstance(entry, dict):
            continue
        p = cast("dict[str, Any]", entry)
        if p.get("id") in WRITING and p.get("active", True) is not False:
            found.append(f"- {p.get('title')}: {p.get('statement')}")
    return found


def context_text(root: Path, principles: dict[str, Any]) -> str:
    lines = [
        "alpha: what the product does is in docs/alpha/specification.md and how the "
        "work is done in CONTRIBUTING.md; read the parts that bear on your change "
        "before changing anything, and record a decision there with the decision "
        "skill."
    ]
    exceptions = exception_rows(root)
    if exceptions:
        lines += ["Exceptions in effect (CONTRIBUTING.md):"]
        lines += [e.row for e in exceptions]
    overrides = overrides_in_effect(principles)
    if overrides:
        lines += ["Principle overrides:", *(f"- {o}" for o in overrides)]
    writing = writing_principles(principles)
    if writing:
        lines += [
            "Write code by these principles (docs/alpha/principles.toml):",
            *writing,
        ]
    return "\n".join(lines)


def agent_files_path(root: Path, agent_id: str) -> Path:
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
ALPHA_GLOB = f"{ALPHA_DIR}/**"
# What a shell command may not write, besides alpha's own folder: the files
# whose change switches alpha's hooks off. An edit of the settings files is
# judged entry by entry (guard_paths), a shell write can't be.
SHELL_WIRING = (SETTINGS, LOCAL_SETTINGS, PRINCIPLES)


def _covers(rel: str, folder: str) -> bool:
    return rel == folder or rel.startswith(f"{folder}/") or folder.startswith(f"{rel}/")


def protected_glob(
    rel: str, principles: dict[str, Any], shell: bool = False
) -> str | None:
    """The protection `rel` falls under, or None. `shell`: a shell command's
    write, which may not touch the hook wiring at all."""
    rel = rel.rstrip("/")
    if _covers(rel, STATE_DIR):
        return STATE_GLOB
    if rel.startswith(f"{BASELINE_DIR}/"):
        for glob in principles.get("protected", {}).get("paths", []):
            if matches(rel, [str(glob)]):
                return str(glob)
    if rel.startswith(f"{NOTES_DIR}/"):
        return None  # a paused session's resume notes, gitignored
    if _covers(rel, ALPHA_DIR):
        return ALPHA_GLOB
    if shell and any(rel == w or w.startswith(f"{rel}/") for w in SHELL_WIRING):
        return rel
    for glob in principles.get("protected", {}).get("paths", []):
        if matches(rel, [str(glob)]):
            return str(glob)
    return None


def alpha_hook_entries(text: str) -> list[str] | None:
    """alpha's hook entries in a settings file's text, as comparable strings
    (event, matcher, command), or None when it isn't a JSON object."""
    try:
        data: object = json.loads(text) if text.strip() else {}
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    found: list[str] = []
    hooks: object = cast("dict[str, Any]", data).get("hooks")
    events = cast("dict[str, Any]", hooks) if isinstance(hooks, dict) else {}
    for event, groups in events.items():
        listed = cast("list[object]", groups) if isinstance(groups, list) else []
        for group in listed:
            if not isinstance(group, dict):
                continue
            g = cast("dict[str, Any]", group)
            raw: object = g.get("hooks")
            entries = cast("list[object]", raw) if isinstance(raw, list) else []
            for entry in entries:
                command: object = (
                    cast("dict[str, Any]", entry).get("command")
                    if isinstance(entry, dict)
                    else None
                )
                if isinstance(command, str) and f"{HOOKS_DIR}/" in command:
                    found.append(f"{event}\t{g.get('matcher', '')}\t{command}")
    return sorted(found)


def disables_hooks(text: str) -> bool:
    try:
        data: object = json.loads(text) if text.strip() else {}
    except ValueError:
        return False
    return isinstance(data, dict) and bool(
        cast("dict[str, Any]", data).get("disableAllHooks")
    )


def protected_message(rel: str, glob: str, principles: dict[str, Any]) -> str:
    if glob == ALPHA_GLOB:
        how = (
            " Change the answers with alpha answers write, then alpha update."
            if rel.endswith("project.json")
            else " alpha update rewrites alpha's own files."
        )
        return (
            f"{rel} is alpha's own ({ALPHA_DIR}/): its hooks, checks and answers, "
            f"which only {UNINSTALL} switches off.{how} Ask the user if it's wrong."
        )
    if rel in SHELL_WIRING:
        return (
            f"{rel} wires alpha's hooks, so a shell command may not write it; only "
            f"{UNINSTALL} switches the hooks off. Edit it with the Edit tool (a "
            "permission, say), or ask the user."
        )
    if glob == STATE_GLOB:
        return (
            f"{rel} is protected: alpha's hooks keep their state there "
            f"({STATE_DIR}/), including the review record, and nothing else may "
            "write or delete it; only /alpha:uninstall switches alpha's hooks off. "
            "Read it if you need to; ask the user if it's wrong."
        )
    head = (
        f"{rel} is protected (`{glob}` in docs/alpha/principles.toml), so Claude can't "
        "edit it."
    )
    if rel.startswith(f"{BASELINE_DIR}/"):
        return (
            f"{head} Baselines shrink by themselves: running the check tightens "
            "the file when findings are fixed, and you commit it. To keep a new "
            "finding, add a row to CONTRIBUTING.md's Exceptions table naming the "
            "check and why, then run alpha baseline capture <project> --check <id>."
        )
    protected = principles.get("protected", {})
    if glob in [str(g) for g in protected.get("extra", [])]:
        return f"{head} Ask the user to change it by hand."
    comp = next(
        (
            c
            for c in components_for(rel, principles)
            if rel in [str(p) for p in c.get("lockfiles", [])]
        ),
        None,
    )
    if comp is not None:
        setup = comp.get("commands", {}).get("setup")
        hint = setup if isinstance(setup, str) and setup else "your package manager"
        return (
            f"{head} Lockfiles change only through the package manager (e.g. {hint})."
        )
    return f"{head} Secrets belong in the environment, never in files Claude edits."
