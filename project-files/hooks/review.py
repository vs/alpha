"""Review debt for the principles reviewer: what changed since the last review.

The last review is a git tree id: a snapshot of the working tree (committed or
not) that passed review. Debt is the diff from it to a fresh snapshot.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402

STATE = "review.json"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
INDEX_FILE = "alpha-review-index"
_STALE_LOCK_SECONDS = 120


class SnapshotError(Exception):
    """git couldn't snapshot the working tree; the message says why."""


def _run(
    root: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # quotepath off: non-ASCII names as they are
            ["git", "-c", "core.quotepath=false", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except OSError:
        return None


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str | None:
    proc = _run(root, *args, env=env)
    return proc.stdout if proc is not None and proc.returncode == 0 else None


def _must(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    proc = _run(root, *args, env=env)
    if proc is None:
        raise SnapshotError("git couldn't be run")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        raise SnapshotError(f"git {args[0]} failed: {detail[0] if detail else '?'}")
    return proc.stdout


def snapshot(root: Path) -> str:
    """The working tree's tree id, through a scratch index in the git directory
    (the real index is untouched). Ignored files and alpha's state stay out.
    The scratch index persists, so unchanged files aren't hashed again."""
    git_dir = Path(_must(root, "rev-parse", "--absolute-git-dir").strip())
    index = git_dir / INDEX_FILE
    lock = git_dir / f"{INDEX_FILE}.lock"
    try:  # a hook killed mid-snapshot leaves its lock behind
        if time.time() - lock.stat().st_mtime > _STALE_LOCK_SECONDS:
            lock.unlink()
    except OSError:
        pass
    env = {**os.environ, "GIT_INDEX_FILE": str(index)}
    head = _git(root, "rev-parse", "--verify", "-q", "HEAD^{tree}")
    if head and index.is_file():
        # --reset keeps the stat info of unchanged entries, and doesn't refuse
        # an index that is out of date with the working tree as -m does.
        _must(root, "read-tree", "--reset", head.strip(), env=env)
    elif head:
        _must(root, "read-tree", head.strip(), env=env)
    else:
        _must(root, "read-tree", "--empty", env=env)
    # Not an exclude pathspec: in generated projects the state folder is
    # gitignored, and git add exits 1 when a pathspec names an ignored path.
    _must(root, "add", "-A", "--", ".", env=env)
    _must(
        root,
        "rm",
        "-rqf",
        "--cached",
        "--ignore-unmatch",
        "--",
        _common.STATE_DIR,
        env=env,
    )
    return _must(root, "write-tree", env=env).strip()


def load_state(root: Path) -> dict[str, Any]:
    """The saved state; {} when there is none, {"unreadable": True} when the
    file exists but can't be read."""
    path = _common.state_path(root, STATE)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"unreadable": True}
    if not isinstance(data, dict):
        return {"unreadable": True}
    state = cast("dict[str, Any]", data)
    findings: object = state.get("findings", [])
    if not isinstance(findings, list) or not all(
        _well_formed(f) for f in cast("list[object]", findings)
    ):
        return {"unreadable": True}
    return state


_FINDING_TEXT = ("id", "principle", "file", "problem", "fix")


def _well_formed(finding: object) -> bool:
    """A finding as review_record.py writes it."""
    if not isinstance(finding, dict):
        return False
    f = cast("dict[str, Any]", finding)
    return (
        all(isinstance(f.get(k), str) for k in _FINDING_TEXT)
        and isinstance(f.get("line"), int)
        and isinstance(f.get("accepted", False), bool)
    )


def save_state(root: Path, state: dict[str, Any]) -> None:
    """Write the state in one step, so a killed hook never leaves half a file."""
    path = _common.state_path(root, STATE)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f"{STATE}.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(state, indent=2) + "\n")
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise


def _start_tree(root: Path) -> str:
    """Where review starts without state: the last pushed commit when there is
    an upstream (so committed, unpushed work stays unreviewed), else HEAD."""
    upstream = _git(root, "merge-base", "HEAD", "@{upstream}")
    rev = f"{upstream.strip()}^{{tree}}" if upstream else "HEAD^{tree}"
    tree = _git(root, "rev-parse", "--verify", "-q", rev)
    return tree.strip() if tree else EMPTY_TREE


def ensure_state(root: Path) -> dict[str, Any]:
    """The review state, created when missing or unreadable."""
    state = load_state(root)
    if not isinstance(state.get("reviewed_tree"), str):
        start = _start_tree(root)
        fresh: dict[str, Any] = {
            "reviewed_tree": start,
            "findings": [],
            "reviewed_for": "",
        }
        if state.get("unreadable"):
            fresh["notice"] = (
                "alpha: the review state was unreadable, so review restarted from "
                "the last pushed commit (or HEAD)."
            )
        save_state(root, fresh)
        state = fresh
    return state


def _numstat(root: Path, old: str, new: str) -> list[tuple[int, str]]:
    out = _git(root, "diff", "--numstat", "-z", "--no-renames", old, new)
    if not out:
        return []
    rows: list[tuple[int, str]] = []
    for entry in out.split("\0"):
        parts = entry.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        count = (int(added) if added.isdigit() else 0) + (
            int(deleted) if deleted.isdigit() else 0
        )
        rows.append((count, path))
    return rows


def debt(root: Path, principles: dict[str, Any]) -> dict[str, Any]:
    """Changed files since the last review, their size, and the risky ones."""
    state = ensure_state(root)
    reviewed = str(state["reviewed_tree"])
    current = snapshot(root)  # SnapshotError propagates: callers fail closed
    empty: dict[str, Any] = {
        "files": [],
        "counted_files": 0,
        "counted_lines": 0,
        "risky": [],
        "tree": current,
    }
    if current == reviewed:
        return empty
    review: dict[str, Any] = principles.get("review", {})
    excluded = [str(g) for g in review.get("exclude", [])]
    risk_globs = [str(g) for g in review.get("risk_paths", [])]
    manifests: list[str] = []
    new_folders: list[str] = []
    for comp in principles.get("components", []):
        manifests += [str(m) for m in comp.get("manifests", [])]
        path = str(comp.get("path", ".")).strip("/")
        if (
            path not in ("", ".")
            and _git(root, "cat-file", "-e", f"{reviewed}:{path}") is None
        ):
            new_folders.append(path)
    files: list[str] = []
    risky: list[str] = []
    counted_files = counted_lines = 0
    for count, path in _numstat(root, reviewed, current):
        files.append(path)
        if not _common.matches(path, excluded):
            counted_files += 1
            counted_lines += count
        if (
            _common.matches(path, risk_globs)
            or path in manifests
            or any(path.startswith(f"{folder}/") for folder in new_folders)
        ):
            risky.append(path)
    return {
        "files": files,
        "counted_files": counted_files,
        "counted_lines": counted_lines,
        "risky": risky,
        "tree": current,
    }


def review_due(principles: dict[str, Any], debt: dict[str, Any]) -> str | None:
    """Why the reviewer must run now, or None."""
    if not debt["files"]:
        return None
    review: dict[str, Any] = principles.get("review", {})
    if review.get("mode") == "every-task":
        return "review mode is every-task"
    if debt["risky"]:
        return f"risky paths changed: {', '.join(debt['risky'])}"
    max_lines = int(review.get("max_lines", 200))
    max_files = int(review.get("max_files", 5))
    if debt["counted_lines"] > max_lines or debt["counted_files"] >= max_files:
        return (
            f"{debt['counted_lines']} lines in {debt['counted_files']} files changed "
            f"since the last review (limits: max_lines {max_lines}, "
            f"max_files {max_files})"
        )
    return None


DIFF_LINES = 1500
USAGE = (
    "Run it as: python3 .claude/alpha/hooks/review.py brief (or snapshot, or "
    "absorb <before-tree> <after-tree>), from the root of an alpha project "
    "(one with docs/principles.toml)."
)


def _relevant_principles(
    principles: dict[str, Any], files: list[str]
) -> list[dict[str, Any]]:
    """Active principles the reviewer checks that apply to the changed files."""
    touched: set[str] = set()
    outside = False
    for path in files:
        comp = _common.component_for(path, principles)
        if comp is None:
            outside = True
        else:
            touched.add(str(comp.get("name")))
    chosen: list[dict[str, Any]] = []
    for p in principles.get("principles", []):
        if not p.get("active") or "reviewer" not in p.get("checked_by", []):
            continue
        names = {str(n) for n in p.get("components", [])}
        if outside or names & touched:
            chosen.append(cast("dict[str, Any]", p))
    return chosen


def _touched(principles: dict[str, Any], files: list[str]) -> set[str] | None:
    """Names of the components the files belong to; None when one is outside
    every component, so all of them count."""
    touched: set[str] = set()
    for path in files:
        comp = _common.component_for(path, principles)
        if comp is None:
            return None
        touched.add(str(comp.get("name")))
    return touched


def _params(params: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in params.items())


def _principle_line(p: dict[str, Any], touched: set[str] | None) -> str:
    line = f"- {p.get('id')} ({p.get('title')}): {p.get('statement')}"
    comps = ", ".join(str(c) for c in p.get("components", []))
    line += f" [components: {comps}]"
    params: dict[str, Any] = p.get("params", {}) or {}
    if params:
        line += f" [params: {_params(params)}]"
    per = p.get("component_params", {})
    if isinstance(per, dict):
        for name, extra in cast("dict[str, Any]", per).items():
            if isinstance(extra, dict) and (touched is None or name in touched):
                line += f" [{name}: {_params(cast('dict[str, Any]', extra))}]"
    if p.get("override_decision"):
        line += f" [override: {p['override_decision']}]"
    return line


def _stack_rules(principles: dict[str, Any], touched: set[str] | None) -> list[str]:
    """The stack rules of the changed components, each once with its components."""
    found: dict[str, tuple[str, list[str]]] = {}
    for comp in principles.get("components", []):
        name = str(comp.get("name"))
        if touched is not None and name not in touched:
            continue
        for r in comp.get("rules", []):
            _, names = found.setdefault(str(r.get("id")), (str(r.get("rule")), []))
            names.append(name)
    return [
        f"- {rule_id}: {rule} [components: {', '.join(names)}]"
        for rule_id, (rule, names) in found.items()
    ]


def _diff(root: Path, old: str, new: str, leave_out: list[str]) -> list[str]:
    """The diff, without the files in leave_out (lockfiles: long, and only
    the package manager writes them)."""
    excluded = [f":(exclude,literal){path}" for path in leave_out]
    out = _git(root, "diff", "--no-renames", old, new, "--", ".", *excluded) or ""
    lines = out.splitlines()
    if len(lines) <= DIFF_LINES:
        return lines
    shown = lines[:DIFF_LINES]
    rest: list[str] = []
    current = ""
    for i, line in enumerate(lines):
        if line.startswith("diff --git "):
            current = line.split(" b/", 1)[-1]
            if i >= DIFF_LINES and current not in rest:
                rest.append(current)
        elif i == DIFF_LINES and current and current not in rest:
            rest.append(current)  # cut in the middle of this file
    return [
        *shown,
        f"… diff truncated; read the remaining files directly: {', '.join(rest)}",
    ]


def brief(root: Path) -> str:
    """Everything the reviewer needs: the tree it reviews, the principles and
    decisions in effect, open findings, and the unreviewed diff."""
    principles = _common.load_principles(root) or {}
    state = ensure_state(root)
    reviewed = str(state["reviewed_tree"])
    current = snapshot(root)
    # The recorder accepts a report only on a tree a brief handed out.
    state["briefed"] = [*state.get("briefed", []), current][-5:]
    save_state(root, state)
    stats = _numstat(root, reviewed, current)
    files = [path for _, path in stats]
    records, _warnings = _common.decision_index(root)
    lines = [f"Tree: {current}", f"Reviewed: {reviewed}", "", "## Principles", ""]
    touched = _touched(principles, files)
    lines += [
        _principle_line(p, touched) for p in _relevant_principles(principles, files)
    ]
    rules = _stack_rules(principles, touched)
    if rules:
        lines += ["", "## Stack rules", "", *rules]
    lines += ["", "## Decisions", ""]
    lines += [
        f"- {n:04d} {title} ({path})"
        for n, title, status, path in records
        if status == "accepted"
    ]
    accepted = [f for f in state.get("findings", []) if f.get("accepted")]
    if accepted:
        lines += ["", "## Accepted findings (don't report these again)", ""]
        lines += [
            f"- {f['id']} {f['principle']} {f['file']}:{f['line']}: {f['problem']}"
            for f in accepted
        ]
    findings = [f for f in state.get("findings", []) if not f.get("accepted")]
    if findings:
        lines += ["", "## Open findings", ""]
        lines += [
            f"- {f['id']} {f['principle']} {f['file']}:{f['line']}: {f['problem']}"
            for f in findings
        ]
    lines += ["", "## Changed files", ""]
    lines += [f"{count}\t{path}" for count, path in stats]
    lockfiles = {
        str(lock)
        for comp in principles.get("components", [])
        for lock in comp.get("lockfiles", [])
    }
    changed_locks = [path for path in files if path in lockfiles]
    lines += ["", "## Diff", ""]
    if changed_locks:
        lines += [
            f"Lockfiles changed (diff left out): {', '.join(changed_locks)}",
            "",
        ]
    lines += _diff(root, reviewed, current, changed_locks)
    return "\n".join(lines) + "\n"


def main() -> None:
    _common.check_python()
    root = _common.project_root({})
    args = sys.argv[1:]
    valid = args in (["brief"], ["snapshot"]) or (
        len(args) == 3 and args[0] == "absorb"
    )
    if not valid or not (root / "docs" / "principles.toml").is_file():
        print(USAGE, file=sys.stderr)
        sys.exit(1)
    try:
        if args[0] == "brief":
            print(brief(root), end="")
        elif args[0] == "snapshot":
            print(snapshot(root))
        else:
            if not absorb(root, args[1], args[2]):
                print(
                    "review.py: some of alpha's changes clash with edits the "
                    "reviewer hasn't seen; they stay under review.",
                    file=sys.stderr,
                )
                sys.exit(1)
    except SnapshotError as e:
        print(
            f"review.py: can't snapshot the working tree ({e}). Fix that, then run "
            "the brief again.",
            file=sys.stderr,
        )
        sys.exit(1)


_ACCEPTS = re.compile(r"F-[0-9a-f]{6}")


def accepted_in_log(root: Path) -> set[str]:
    """Finding ids that decision records accept on an "Accepts:" header line."""
    ids: set[str] = set()
    for _n, _title, _status, path in _common.decision_index(root)[0]:
        try:
            head = (root / path).read_text(encoding="utf-8").splitlines()[:20]
        except (OSError, UnicodeDecodeError):
            continue
        for line in head:
            if line.startswith("Accepts:"):
                ids.update(_ACCEPTS.findall(line))
    return ids


def gate(root: Path, principles: dict[str, Any]) -> str | None:
    """Why Claude can't finish yet, review-wise, or None."""
    state = ensure_state(root)
    findings: list[dict[str, Any]] = list(state.get("findings", []))
    still_open = [f for f in findings if not f.get("accepted")]
    if still_open:
        listing = "\n".join(
            f"{f['id']} {f['principle']} {f['file']}:{f['line']}: {f['problem']} "
            f"Fix: {f['fix']}"
            for f in still_open
        )
        first = still_open[0]["id"]
        return (
            f"alpha review: open findings:\n{listing}\nFix them and run the "
            "principles-reviewer agent again. If one can't or shouldn't be fixed, "
            f'ask the user; they accept it by replying "accept {first}".'
        )
    logged = accepted_in_log(root)
    unrecorded = [str(f["id"]) for f in findings if f["id"] not in logged]
    if unrecorded:
        lines = ", ".join(f"Accepts: {i}" for i in unrecorded)
        return (
            "alpha review: the user accepted findings that aren't in the decision "
            "log yet. Record them with the decision skill, one header line each: "
            f"{lines}."
        )
    if findings:
        # Every finding is accepted and recorded: the reviewed tree passes.
        # Later edits, such as the decision record itself, are measured from it.
        state["reviewed_tree"] = state["reviewed_for"]
        state["findings"] = []
        save_state(root, state)
    reason = review_due(principles, debt(root, principles))
    if reason:
        return (
            f"alpha review: run the principles-reviewer agent before finishing "
            f"({reason})."
        )
    return None


def push_blocker(root: Path, principles: dict[str, Any]) -> str | None:
    """Why a push or pull request must wait for the reviewer, or None.
    Unlike the Stop gate, any unreviewed change counts, whatever its size."""
    state = ensure_state(root)
    logged = accepted_in_log(root)
    pending = [
        str(f["id"])
        for f in state.get("findings", [])
        if not f.get("accepted") or f["id"] not in logged
    ]
    if pending:
        return (
            "Nothing leaves the machine unreviewed: resolve the review findings "
            f"first ({', '.join(pending)}): fix them and run the principles-reviewer "
            "again, or have the user accept them and record that in the decision log."
        )
    try:
        files = debt(root, principles)["files"]
    except SnapshotError as e:
        return (
            "Nothing leaves the machine unreviewed, but alpha can't measure the "
            f"review debt ({e}). Fix that and retry, or ask the user to push by hand."
        )
    if files:
        noun = "file" if len(files) == 1 else "files"
        return (
            "Nothing leaves the machine unreviewed: run the principles-reviewer "
            f"agent first ({len(files)} {noun} changed since the last review)."
        )
    return None


_ALPHA_IDENTITY = {
    "GIT_AUTHOR_NAME": "alpha",
    "GIT_AUTHOR_EMAIL": "alpha@localhost",
    "GIT_COMMITTER_NAME": "alpha",
    "GIT_COMMITTER_EMAIL": "alpha@localhost",
}


def note_turn_end(root: Path) -> None:
    """Remember the tree Claude leaves at a Stop; the last Stop of a turn wins."""
    state = ensure_state(root)
    try:
        state["left_tree"] = snapshot(root)
    except SnapshotError:
        state.pop("left_tree", None)
    save_state(root, state)


def _commit(root: Path, tree: str) -> str | None:
    """A throwaway commit object for a tree, so merge-tree can use it."""
    env = {**os.environ, **_ALPHA_IDENTITY}
    out = _git(root, "commit-tree", tree, "-m", "alpha review snapshot", env=env)
    return out.strip() if out else None


def _carry(root: Path, state: dict[str, Any], left: str, right: str) -> bool:
    """Carry the change from tree `left` to tree `right` onto
    state["reviewed_tree"], with a three-way merge based on `left`. Returns
    False, carrying nothing, on a conflict or anything git can't do."""
    reviewed = state.get("reviewed_tree")
    if not isinstance(reviewed, str):
        return False
    if right == left:
        return True
    commits = [_commit(root, t) for t in (left, reviewed, right)]
    if not all(commits):
        return False
    base, ours, theirs = cast("list[str]", commits)
    merged = _git(
        root, "merge-tree", "--write-tree", f"--merge-base={base}", ours, theirs
    )
    if not merged:
        return False
    state["reviewed_tree"] = merged.splitlines()[0].strip()
    return True


def absorb_outside_changes(root: Path) -> None:
    """Changes made between Claude's turns (the user's edits, a pull) aren't
    Claude's work: carry them onto the reviewed tree with a three-way merge
    based on the tree Claude left. Claude's own unreviewed edits stay debt; on
    a conflict, or anything git can't do, nothing is absorbed."""
    state = load_state(root)
    left = state.get("left_tree")
    if not isinstance(left, str) or not isinstance(state.get("reviewed_tree"), str):
        return
    state.pop("left_tree", None)
    try:
        current = snapshot(root)
    except SnapshotError:
        save_state(root, state)
        return
    _carry(root, state, left, current)
    save_state(root, state)


def _entries(root: Path, tree: str, paths: list[str]) -> dict[str, tuple[str, str]]:
    """path -> (mode, blob id) of the files `paths` names in a tree."""
    out = _git(root, "ls-tree", "-z", tree, "--", *paths)
    entries: dict[str, tuple[str, str]] = {}
    for row in (out or "").split("\0"):
        meta, _, path = row.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and path:
            entries[path] = (parts[0], parts[2])
    return entries


def _carry_paths(root: Path, state: dict[str, Any], before: str, after: str) -> bool:
    """Carry each path alpha changed (before to after) that the reviewed tree
    still has as `before` did; the rest stay debt. True when none was left."""
    reviewed = state.get("reviewed_tree")
    names = _git(root, "diff", "--name-only", "-z", "--no-renames", before, after)
    if not isinstance(reviewed, str) or names is None:
        return False
    paths = [p for p in names.split("\0") if p]
    was = _entries(root, before, paths)
    now = _entries(root, reviewed, paths)
    new = _entries(root, after, paths)
    take = [p for p in paths if now.get(p) == was.get(p)]
    if take:
        git_dir = Path(_must(root, "rev-parse", "--absolute-git-dir").strip())
        index = git_dir / f"{INDEX_FILE}.absorb"
        env = {**os.environ, "GIT_INDEX_FILE": str(index)}
        try:
            _must(root, "read-tree", reviewed, env=env)
            for p in take:
                if p in new:
                    mode, blob = new[p]
                    info = f"{mode},{blob},{p}"
                    _must(root, "update-index", "--add", "--cacheinfo", info, env=env)
                else:
                    _must(root, "update-index", "--force-remove", "--", p, env=env)
            state["reviewed_tree"] = _must(root, "write-tree", env=env).strip()
        except SnapshotError:
            return False
        finally:
            index.unlink(missing_ok=True)
    return len(take) == len(paths)


def absorb(root: Path, before: str, after: str) -> bool:
    """Treat alpha's update, the change from tree `before` to tree `after`, as
    reviewed. On a conflict, carry the paths that don't clash. True when all of
    it was carried."""
    state = load_state(root)
    if not isinstance(state.get("reviewed_tree"), str):
        return True  # no state yet, or an unreadable one: ensure_state starts clean
    done = _carry(root, state, before, after) or _carry_paths(
        root, state, before, after
    )
    save_state(root, state)
    return done


if __name__ == "__main__":
    main()
