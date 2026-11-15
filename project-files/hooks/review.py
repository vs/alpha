"""alpha's principles review, kept in git notes on the trees it reviewed.

The review runs once, before work reaches main (rewrite spec, R9 and R10).
Reviewing a tree adds a note to that tree object under refs/notes/alpha-review.
To find the last review, the branch's history since main is walked, each
commit mapped to its tree; after a rebase, the newest note recorded for the
branch. Only the files the branch changed since that review are reviewed, and
a review's findings are the only thing that blocks after it: the next review
is a fix check, which judges them and reviews afresh only the changed files
no finding names, so a fix never starts another full review. The notes stay
local; another clone reviews again.

Usage, from the project root: review.py brief
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).parent))
import _common
import untested

NOTES_REF = "alpha-review"
RENDERED_REF = "alpha-rendered"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
MAIN_REFS = (
    "refs/remotes/origin/HEAD",
    "refs/remotes/origin/main",
    "refs/remotes/origin/master",
    "refs/heads/main",
    "refs/heads/master",
)
STATUSES = ("open", "fixed", "accepted")
IDENTITY = {
    "GIT_AUTHOR_NAME": "alpha",
    "GIT_AUTHOR_EMAIL": "alpha@localhost",
    "GIT_COMMITTER_NAME": "alpha",
    "GIT_COMMITTER_EMAIL": "alpha@localhost",
}


class ReviewError(Exception):
    """The review can't run as things are; the message says what to do."""


def _run(
    root: Path, *args: str, stdin: str | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # quotepath off: non-ASCII names as they are
            ["git", "-c", "core.quotepath=false", *args],
            cwd=root,
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, **(env or {})},
        )
    except OSError:
        return None


def _git(root: Path, *args: str) -> str | None:
    proc = _run(root, *args)
    return proc.stdout if proc is not None and proc.returncode == 0 else None


def main_base(root: Path) -> str | None:
    """Where this branch leaves main: the merge base with the first main ref
    that exists, or None when the repository has none."""
    for ref in MAIN_REFS:
        if _git(root, "rev-parse", "--verify", "-q", ref):
            out = _git(root, "merge-base", "HEAD", ref)
            return out.strip() if out else None
    return None


def tree_of(root: Path, commit: str | None) -> str:
    out = (
        _git(root, "rev-parse", "--verify", "-q", f"{commit}^{{tree}}")
        if commit
        else None
    )
    return out.strip() if out else EMPTY_TREE


def current_branch(root: Path) -> str:
    return (_git(root, "branch", "--show-current") or "").strip()


def _noted(root: Path, ref: str) -> dict[str, str]:
    """The objects a notes ref annotates, each with its note's blob."""
    out = _git(root, "notes", f"--ref={ref}", "list") or ""
    pairs = (line.split() for line in out.splitlines())
    return {p[1]: p[0] for p in pairs if len(p) == 2}


def read_note(root: Path, obj: str) -> dict[str, Any] | None:
    out = _git(root, "notes", f"--ref={NOTES_REF}", "show", obj)
    if not out:
        return None
    try:
        data: object = json.loads(out)
    except ValueError:
        return None
    return cast("dict[str, Any]", data) if isinstance(data, dict) else None


def write_note(root: Path, tree: str, note: dict[str, Any]) -> None:
    text = json.dumps(note, indent=2, sort_keys=True)
    proc = _run(
        root,
        "notes",
        f"--ref={NOTES_REF}",
        "add",
        "-f",
        "-F",
        "-",
        tree,
        stdin=text,
        env=IDENTITY,
    )
    if proc is None or proc.returncode != 0:
        detail = proc.stderr.strip() if proc is not None else "git couldn't run"
        raise ReviewError(f"git couldn't record the review on {tree}: {detail}")


def last_review(root: Path) -> tuple[str, dict[str, Any]] | None:
    """The last reviewed tree and its note: the first commit since main whose
    tree has one, walked newest first in topological order; when a rebase
    gave every commit a new tree, the newest note recorded for this branch.
    A note on main's history carries nothing into the branch."""
    noted = _noted(root, NOTES_REF)
    if not noted:
        return None
    base = main_base(root)
    walk = _git(
        root, "log", "--topo-order", "--format=%T", f"{base}..HEAD" if base else "HEAD"
    )
    for tree in (walk or "").split():
        if tree in noted:
            note = read_note(root, tree)
            if note is not None:
                return tree, note
    branch = current_branch(root)
    on_main: set[str] = (
        set((_git(root, "log", "--format=%T", base) or "").split()) if base else set()
    )
    newest: tuple[int, str, dict[str, Any]] | None = None
    for obj in noted:
        if obj in on_main:
            continue
        note = read_note(root, obj)
        if note is None or not branch or note.get("branch") != branch:
            continue
        stamp = note.get("recorded")
        when = stamp if isinstance(stamp, int) else 0
        if newest is None or when > newest[0]:
            newest = (when, obj, note)
    return (newest[1], newest[2]) if newest else None


def open_findings(note: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw: object = note.get("findings", []) if note else []
    items = cast("list[object]", raw) if isinstance(raw, list) else []
    return [
        cast("dict[str, Any]", f)
        for f in items
        if isinstance(f, dict) and cast("dict[str, Any]", f).get("status") == "open"
    ]


def _blobs(root: Path, treeish: str) -> dict[str, str]:
    out = _git(root, "ls-tree", "-r", "-z", treeish) or ""
    found: dict[str, str] = {}
    for row in out.split("\0"):
        meta, _, path = row.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            found[path] = parts[2]
    return found


def render_blobs(root: Path) -> dict[str, str]:
    """The blobs of alpha's own render at HEAD (alpha.rendered): files equal
    to it are alpha's writes, not the branch's work."""
    noted = _noted(root, RENDERED_REF)
    if not noted:
        return {}
    for commit in (_git(root, "rev-list", "--topo-order", "HEAD") or "").split():
        if commit in noted:
            render = (_git(root, "cat-file", "blob", noted[commit]) or "").strip()
            return _blobs(root, render) if render else {}
    return {}


def _names(root: Path, old: str, new: str) -> list[str]:
    out = _git(root, "diff", "--name-only", "-z", "--no-renames", old, new) or ""
    return [p for p in out.split("\0") if p]


def files_to_review(root: Path, last_tree: str | None) -> list[str]:
    """What the branch changed since main, and since the last review if any,
    leaving out each file whose content is alpha's render."""
    head = tree_of(root, "HEAD")
    files = _names(root, tree_of(root, main_base(root)), head)
    if last_tree is not None:
        since = set(_names(root, last_tree, head))
        files = [f for f in files if f in since]
    render = render_blobs(root)
    if render:
        current = _blobs(root, head)
        files = [
            f for f in files if render.get(f) is None or render[f] != current.get(f)
        ]
    return files


def dirty(root: Path) -> list[str]:
    out = _git(root, "status", "--porcelain", "--untracked-files=no") or ""
    return [line[3:] for line in out.splitlines() if line.strip()]


def _briefs_path(root: Path) -> Path:
    common = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    folder = Path(common.strip()) / "alpha" if common else root / ".git" / "alpha"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "briefs.json"


def briefs(root: Path) -> list[dict[str, Any]]:
    try:
        data: object = json.loads(_briefs_path(root).read_text())
    except (OSError, ValueError):
        return []
    items = cast("list[object]", data) if isinstance(data, list) else []
    return [cast("dict[str, Any]", b) for b in items if isinstance(b, dict)]


def _remember(root: Path, brief: dict[str, Any]) -> None:
    kept = [b for b in briefs(root) if b.get("tree") != brief["tree"]][-9:]
    _briefs_path(root).write_text(json.dumps([*kept, brief], indent=2))


def on_risk_path(principles: dict[str, Any], path: str) -> bool:
    globs = [str(g) for g in principles.get("review", {}).get("risk_paths", [])]
    return _common.matches(path, globs)


def accepts_since(root: Path, tree: str | None) -> list[str]:
    """The `Accepts:` lines of the branch's commits since the reviewed tree's
    commit, read in one git call."""
    base = main_base(root)
    out = _git(
        root, "log", "--format=%T%x00%B%x1e", f"{base}..HEAD" if base else "HEAD"
    )
    lines: list[str] = []
    for record in (out or "").split("\x1e"):
        found_tree, _, body = record.strip("\n").partition("\x00")
        if found_tree == tree:
            break
        lines += [line for line in body.splitlines() if line.startswith("Accepts: F-")]
    return lines


DIFF_LINES = 1500


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
    if p.get("override"):
        line += f" [override: {p['override']}]"
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


def _finding_line(f: dict[str, Any]) -> str:
    return f"- {f['id']} {f['principle']} {f['file']}:{f['line']}: {f['problem']}"


def brief(root: Path) -> str:
    """What the principles-reviewer reviews next: a review of the files the
    branch changed since the last one, or a fix check of its open findings."""
    stale = dirty(root)
    if stale:
        raise ReviewError(
            f"tracked files have uncommitted changes ({', '.join(stale[:5])}). The "
            "review covers the committed tree: commit or stash them, then run the "
            "brief again."
        )
    principles = _common.load_principles(root) or {}
    head = tree_of(root, "HEAD")
    last = last_review(root)
    previous = open_findings(last[1]) if last else []
    files = files_to_review(root, last[0] if last else None)
    named = {str(f["file"]) for f in previous}
    fresh = [f for f in files if f not in named]
    base = last[0] if last else tree_of(root, main_base(root))
    kind = "fix-check" if previous else "review"
    _remember(
        root,
        {
            "tree": head,
            "kind": kind,
            "base": base,
            "fresh": fresh,
            "findings": previous,
            "branch": current_branch(root),
        },
    )
    load = str(principles.get("review", {}).get("expected_load", "")) or (
        "not recorded: infer it from the README and deploy config, and say "
        "which load you assumed"
    )
    lines = [
        f"Tree: {head}",
        f"Base: {base}",
        f"Kind: {kind}",
        f"Expected load: {load}",
    ]
    shown = sorted({*fresh, *named})
    touched = _touched(principles, shown)
    lines += ["", "## Principles", ""]
    lines += [
        _principle_line(p, touched) for p in _relevant_principles(principles, shown)
    ]
    rules = _stack_rules(principles, touched)
    if rules:
        lines += ["", "## Stack rules", "", *rules]
    exceptions = _common.exception_rows(root)
    if exceptions:
        lines += ["", "## Exceptions (CONTRIBUTING.md)", ""]
        lines += [e.row for e in exceptions]
    if previous:
        lines += [
            "",
            "## Findings to check (a fix check: report each one's status; raise new "
            "findings only on the files under Review afresh)",
            "",
            *(_finding_line(f) for f in previous),
        ]
        accepts = accepts_since(root, base)
        if accepts:
            lines += ["", "## Accepts trailers since the review", "", *accepts]
    noted = untested.notes(root)
    if noted:
        lines += [
            "",
            "## Source changes Claude says need no test (check each reason)",
            "",
        ]
        lines += [f"- {path}: {reason}" for path, reason in sorted(noted.items())]
    lines += ["", "## Review afresh" if previous else "## Changed files", ""]
    lines += [f"- {path}" for path in fresh] or ["(none)"]
    lines += _changed_visuals(root, base, head, principles, fresh)
    lockfiles = {
        str(lock)
        for comp in principles.get("components", [])
        for lock in comp.get("lockfiles", [])
    }
    changed_locks = [path for path in shown if path in lockfiles]
    lines += ["", "## Diff", ""]
    if changed_locks:
        lines += [f"Lockfiles changed (diff left out): {', '.join(changed_locks)}", ""]
    diffed = [p for p in shown if p not in lockfiles]
    lines += _diff(root, base, head, diffed) if diffed else ["(no diff)"]
    return "\n".join(lines) + "\n"


def gate(root: Path, principles: dict[str, Any]) -> str | None:
    """Why the branch can't reach main yet, or None."""
    stale = dirty(root)
    if stale:
        return (
            "Commit or stash the changes to tracked files first "
            f"({', '.join(stale[:5])}): the review covers the committed tree."
        )
    last = last_review(root)
    previous = open_findings(last[1]) if last else []
    if previous:
        ids = ", ".join(str(f["id"]) for f in previous)
        risky = [
            str(f["id"]) for f in previous if on_risk_path(principles, str(f["file"]))
        ]
        users = (
            f" {', '.join(risky)} touch risk paths: only the user accepts those, by "
            f'replying "accept {risky[0]}".'
            if risky
            else ""
        )
        return (
            f"Nothing reaches main with open review findings ({ids}). Fix them, or "
            "commit why one stands as a trailer, `Accepts: <id> <reason>`, then run "
            f"the principles-reviewer to check them.{users}"
        )
    head = tree_of(root, "HEAD")
    if last is not None and last[0] == head:
        return None
    files = files_to_review(root, last[0] if last else None)
    if not files:
        return None
    noun = "file" if len(files) == 1 else "files"
    return (
        "Nothing reaches main unreviewed: run the principles-reviewer agent first "
        f"({len(files)} {noun} changed since the last review)."
    )


USAGE = (
    "Run it as: python3 .claude/alpha/hooks/review.py brief, from the root of an "
    "alpha project."
)


def main() -> None:
    _common.check_python()
    root = _common.project_root({"cwd": os.getcwd()})
    if sys.argv[1:] != ["brief"] or _common.checkout_of(root.resolve()) is None:
        print(USAGE, file=sys.stderr)
        sys.exit(1)
    try:
        print(brief(root), end="")
    except ReviewError as e:
        print(f"review.py: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
