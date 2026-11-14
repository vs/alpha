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
import _common

STATE = "review.json"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
INDEX_FILE = "alpha-review-index"
_STALE_LOCK_SECONDS = 120


class SnapshotError(Exception):
    pass


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
    if not isinstance(finding, dict):
        return False
    f = cast("dict[str, Any]", finding)
    return (
        all(isinstance(f.get(k), str) for k in _FINDING_TEXT)
        and isinstance(f.get("line"), int)
        and isinstance(f.get("accepted", False), bool)
    )


def save_state(root: Path, state: dict[str, Any]) -> None:
    path = _common.state_path(root, STATE)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f"{STATE}.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(state, indent=2) + "\n")
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise


MAIN_REFS = (
    "refs/remotes/origin/HEAD",
    "refs/remotes/origin/main",
    "refs/remotes/origin/master",
    "refs/heads/main",
    "refs/heads/master",
)


def main_base(root: Path) -> str | None:
    """Where this checkout's own work leaves main. A pushed feature branch isn't
    reviewed work, so the branch's upstream doesn't count."""
    for ref in MAIN_REFS:
        if _git(root, "rev-parse", "--verify", "-q", ref):
            out = _git(root, "merge-base", "HEAD", ref)
            if out:
                return out.strip()
    head = _git(root, "rev-parse", "--verify", "-q", "HEAD")
    return head.strip() if head else None


def _tree(root: Path, commit: str | None) -> str:
    out = _git(root, "rev-parse", "--verify", "-q", f"{commit}^{{tree}}")
    return out.strip() if commit and out else EMPTY_TREE


def ensure_state(root: Path) -> dict[str, Any]:
    state = load_state(root)
    base = main_base(root)
    if not isinstance(state.get("reviewed_tree"), str):
        fresh: dict[str, Any] = {
            "reviewed_tree": _tree(root, base),
            "findings": [],
            "reviewed_for": "",
            "base": base,
        }
        if state.get("unreadable"):
            fresh["notice"] = (
                "alpha: the review state was unreadable, so review restarted from "
                "where this branch leaves main."
            )
        save_state(root, fresh)
        return fresh
    if base and isinstance(state.get("base"), str) and state["base"] != base:
        _carry(root, state, _tree(root, state["base"]), _tree(root, base))
        state["base"] = base
        save_state(root, state)
    elif base and "base" not in state:
        state["base"] = base
        save_state(root, state)
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
    state = ensure_state(root)
    reviewed = str(state["reviewed_tree"])
    current = snapshot(root)
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
    if not debt["files"]:
        return None
    review: dict[str, Any] = principles.get("review", {})
    if review.get("mode") == "at-merge":
        return None
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
    'absorb <before-tree> <after-tree>, or untested "<why>" <path> ...), from '
    "the root of an alpha project (one with docs/principles.toml)."
)


def _blob(root: Path, rel: str) -> str:
    out = _git(root, "hash-object", "--", rel) if (root / rel).is_file() else None
    return out.strip() if out else "deleted"


def note_untested(root: Path, reason: str, paths: list[str]) -> list[str]:
    """Record why these source changes need no test; returns the paths that
    aren't in the project."""
    rels = [_common.rel_to_root(root, str(Path.cwd() / p)) for p in paths]
    outside = [p for p, rel in zip(paths, rels, strict=True) if rel is None]
    if outside:
        return outside
    state = ensure_state(root)
    kept = [
        n
        for n in state.get("untested", [])
        if n["path"] not in rels and _blob(root, n["path"]) == n["blob"]
    ]
    kept += [
        {"path": rel, "reason": reason, "blob": _blob(root, rel)}
        for rel in rels
        if rel is not None
    ]
    state["untested"] = kept
    save_state(root, state)
    return []


def untested_notes(root: Path) -> dict[str, str]:
    """Paths noted as needing no test, while their content is still the noted one."""
    notes: object = load_state(root).get("untested", [])
    if not isinstance(notes, list):
        return {}
    found: dict[str, str] = {}
    for n in cast("list[object]", notes):
        if isinstance(n, dict):
            note = cast("dict[str, Any]", n)
            path, reason = note.get("path"), note.get("reason")
            if isinstance(path, str) and isinstance(reason, str):
                if _blob(root, path) == note.get("blob"):
                    found[path] = reason
    return found


def _relevant_principles(
    principles: dict[str, Any], files: list[str]
) -> list[dict[str, Any]]:
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
            rest.append(current)
    return [
        *shown,
        f"… diff truncated; read the remaining files directly: {', '.join(rest)}",
    ]


_VISUAL_HINT = re.compile(
    r"#[0-9a-fA-F]{6}\b|\b(?:rgba?|hsla?|oklch|oklab)\(|style=|<style|<svg"
    r"|(?:```|~~~)\s*\{?\.?(?:mermaid|d2|plantuml|puml|dot|graphviz)"
    r"|\.\. (?:mermaid|graphviz|digraph|graph)::"
    r"|\[(?:mermaid|plantuml|graphviz|d2)\b",
    re.IGNORECASE,
)
_PALETTE_CHECK = ".claude/alpha/checks/palette.py"


def _off_palette(root: Path, files: list[str]) -> list[str]:
    """What the palette check finds in the changed files, without failing."""
    if not files or not (root / _PALETTE_CHECK).is_file():
        return []
    try:
        done = subprocess.run(
            [sys.executable, _PALETTE_CHECK, "--advise", *files],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    return done.stdout.splitlines() if done.returncode == 0 else []


def _changed_visuals(
    root: Path, old: str, new: str, principles: dict[str, Any], files: list[str]
) -> list[str]:
    visuals: dict[str, Any] = principles.get("visuals", {})

    def changed(kind: str) -> list[str]:
        globs = [str(g) for g in visuals.get(kind, [])]
        excluded = [str(g) for g in visuals.get("exclude", [])]
        return [
            path
            for path in files
            if _common.matches(path, globs) and not _common.matches(path, excluded)
        ]

    def touches_a_visual(path: str) -> bool:
        diff = _git(root, "diff", "--no-renames", "-U15", old, new, "--", path) or ""
        return any(
            _VISUAL_HINT.search(line)
            for line in diff.splitlines()
            if line[:1] in ("+", " ") and not line.startswith("+++")
        )

    lines: list[str] = []
    text = [*changed("sources"), *filter(touches_a_visual, changed("carriers"))]
    opaque = changed("opaque")
    if text:
        lines += ["", "## Changed visuals (check each against the design language)"]
        lines += ["", *(f"- {path}" for path in text)]
    if opaque:
        lines += ["", "## Changed visuals that aren't text (name them; can't be read)"]
        lines += ["", *(f"- {path}" for path in opaque)]
    advised = visuals.get("palette_check") == "advise"
    off_palette = _off_palette(root, files) if advised else []
    if off_palette:
        lines += [
            "",
            "## Colors outside the palette (judge each: a deliberate exception "
            "is fine, drift is a finding)",
            "",
            *(f"- {found}" for found in off_palette),
        ]
    return lines


def brief(root: Path) -> str:
    principles = _common.load_principles(root) or {}
    state = ensure_state(root)
    reviewed = str(state["reviewed_tree"])
    current = snapshot(root)
    state["briefed"] = [*state.get("briefed", []), current][-5:]
    save_state(root, state)
    stats = _numstat(root, reviewed, current)
    files = [path for _, path in stats]
    records, _warnings = _common.decision_index(root)
    load = str(principles.get("review", {}).get("expected_load", "")) or (
        "not recorded: infer it from the README and deploy config, and say "
        "which load you assumed"
    )
    lines = [f"Tree: {current}", f"Reviewed: {reviewed}", f"Expected load: {load}"]
    lines += ["", "## Principles", ""]
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
    logged = accepted_in_log(root)
    by_user = [f for f in state.get("findings", []) if f.get("accepted")]
    if by_user:
        lines += ["", "## Findings the user accepted (don't report these again)", ""]
        lines += [
            f"- {f['id']} {f['principle']} {f['file']}:{f['line']}: {f['problem']}"
            for f in by_user
        ]
    by_claude = [
        f
        for f in state.get("findings", [])
        if not f.get("accepted") and settled(principles, f, logged)
    ]
    if by_claude:
        lines += [
            "",
            "## Findings Claude accepted (read the decision that accepts each; "
            "report it as a new finding if its reason doesn't hold)",
            "",
        ]
        lines += [
            f"- {f['id']} {f['principle']} {f['file']}:{f['line']}: {f['problem']}"
            for f in by_claude
        ]
    findings = [
        f for f in state.get("findings", []) if not settled(principles, f, logged)
    ]
    if findings:
        lines += ["", "## Open findings", ""]
        lines += [
            f"- {f['id']} {f['principle']} {f['file']}:{f['line']}: {f['problem']}"
            for f in findings
        ]
    untested = untested_notes(root)
    if untested:
        lines += [
            "",
            "## Source changes Claude says need no test (check each reason)",
            "",
        ]
        lines += [f"- {path}: {reason}" for path, reason in sorted(untested.items())]
    lines += ["", "## Changed files", ""]
    lines += [f"{count}\t{path}" for count, path in stats]
    lines += _changed_visuals(root, reviewed, current, principles, files)
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
    root = _common.project_root({"cwd": os.getcwd()})
    args = sys.argv[1:]
    valid = (
        args in (["brief"], ["snapshot"])
        or (len(args) == 3 and args[0] == "absorb")
        or (len(args) >= 3 and args[0] == "untested")
    )
    if not valid or not (root / "docs" / "principles.toml").is_file():
        print(USAGE, file=sys.stderr)
        sys.exit(1)
    try:
        if args[0] == "untested":
            if len(args[1].split()) < 2:
                print(
                    'review.py: give the reason in a few words, e.g. "renames '
                    'the field only", before the paths.',
                    file=sys.stderr,
                )
                sys.exit(1)
            outside = note_untested(root, args[1], args[2:])
            if outside:
                print(
                    f"review.py: {', '.join(outside)} isn't in this project; name "
                    "files from its root.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print("noted: the principles-reviewer checks the reason")
        elif args[0] == "brief":
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


def on_risk_path(principles: dict[str, Any], finding: dict[str, Any]) -> bool:
    globs = [str(g) for g in principles.get("review", {}).get("risk_paths", [])]
    return _common.matches(str(finding.get("file", "")), globs)


def settled(
    principles: dict[str, Any], finding: dict[str, Any], logged: set[str]
) -> bool:
    if finding.get("accepted"):
        return True
    return finding["id"] in logged and not on_risk_path(principles, finding)


def gate(root: Path, principles: dict[str, Any]) -> str | None:
    state = ensure_state(root)
    findings: list[dict[str, Any]] = list(state.get("findings", []))
    logged = accepted_in_log(root)
    still_open = [f for f in findings if not settled(principles, f, logged)]
    if still_open:
        listing = "\n".join(
            f"{f['id']} {f['principle']} {f['file']}:{f['line']}: {f['problem']} "
            f"Fix: {f['fix']}"
            for f in still_open
        )
        risky = [str(f["id"]) for f in still_open if on_risk_path(principles, f)]
        escalate = (
            f" {', '.join(risky)} touch risk paths: only the user accepts those, "
            f'by replying "accept {risky[0]}".'
            if risky
            else ""
        )
        return (
            f"alpha review: open findings:\n{listing}\nFix them and run the "
            "principles-reviewer agent again. A finding you can disprove: record "
            "the disproof with the decision skill, with an `Accepts: <id>` header "
            f"line, and carry on.{escalate}"
        )
    unrecorded = [str(f["id"]) for f in findings if f["id"] not in logged]
    if unrecorded:
        lines = ", ".join(f"Accepts: {i}" for i in unrecorded)
        return (
            "alpha review: the user accepted findings that aren't in the decision "
            "log yet. Record them with the decision skill, one header line each: "
            f"{lines}."
        )
    if findings:
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


def merge_blocker(root: Path, principles: dict[str, Any]) -> str | None:
    state = ensure_state(root)
    logged = accepted_in_log(root)
    pending = [
        str(f["id"])
        for f in state.get("findings", [])
        if not settled(principles, f, logged) or f["id"] not in logged
    ]
    if pending:
        return (
            "Nothing reaches main unreviewed: resolve the review findings first "
            f"({', '.join(pending)}): fix them and run the principles-reviewer "
            "again, or record why one stands with the decision skill (an "
            "`Accepts: <id>` line; a finding on a risk path needs the user's "
            '"accept <id>" too).'
        )
    try:
        files = debt(root, principles)["files"]
    except SnapshotError as e:
        return (
            "Nothing reaches main unreviewed, but alpha can't measure the review "
            f"debt ({e}). Fix that and retry; the snapshot error says what's wrong."
        )
    if files:
        noun = "file" if len(files) == 1 else "files"
        return (
            "Nothing reaches main unreviewed: run the principles-reviewer agent "
            f"first ({len(files)} {noun} changed since the last review)."
        )
    return None


_ALPHA_IDENTITY = {
    "GIT_AUTHOR_NAME": "alpha",
    "GIT_AUTHOR_EMAIL": "alpha@localhost",
    "GIT_COMMITTER_NAME": "alpha",
    "GIT_COMMITTER_EMAIL": "alpha@localhost",
}


def note_turn_end(root: Path) -> None:
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
    out = _git(root, "ls-tree", "-z", tree, "--", *paths)
    entries: dict[str, tuple[str, str]] = {}
    for row in (out or "").split("\0"):
        meta, _, path = row.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and path:
            entries[path] = (parts[0], parts[2])
    return entries


def _carry_paths(root: Path, state: dict[str, Any], before: str, after: str) -> bool:
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
    state = load_state(root)
    if not isinstance(state.get("reviewed_tree"), str):
        return True
    done = _carry(root, state, before, after) or _carry_paths(
        root, state, before, after
    )
    save_state(root, state)
    return done


if __name__ == "__main__":
    main()
