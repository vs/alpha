"""Review debt for the principles reviewer: what changed since the last review.

The last review is a git tree id: a snapshot of the working tree (committed or
not) that passed review. Debt is the diff from it to a fresh snapshot.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).parent))
import _common  # noqa: E402

STATE = "review.json"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_INDEX = "review-index"


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def snapshot(root: Path) -> str | None:
    """The working tree's tree id, through a scratch index (the real one is
    untouched). Ignored files and alpha's state stay out."""
    index = _common.state_path(root, _INDEX)
    env = {**os.environ, "GIT_INDEX_FILE": str(index)}
    head = _git(root, "rev-parse", "--verify", "-q", "HEAD^{tree}")
    start = ("read-tree", head.strip()) if head else ("read-tree", "--empty")
    if _git(root, *start, env=env) is None:
        return None
    if (
        _git(root, "add", "-A", "--", ".", f":(exclude){_common.STATE_DIR}", env=env)
        is None
    ):
        return None
    tree = _git(root, "write-tree", env=env)
    return tree.strip() if tree else None


def load_state(root: Path) -> dict[str, Any]:
    try:
        data = json.loads(_common.state_path(root, STATE).read_text())
    except (OSError, ValueError):
        return {}
    return cast("dict[str, Any]", data) if isinstance(data, dict) else {}


def save_state(root: Path, state: dict[str, Any]) -> None:
    _common.state_path(root, STATE).write_text(json.dumps(state, indent=2) + "\n")


def ensure_state(root: Path) -> dict[str, Any]:
    """The review state; a project without one starts reviewed at HEAD."""
    state = load_state(root)
    if not isinstance(state.get("reviewed_tree"), str):
        head = _git(root, "rev-parse", "--verify", "-q", "HEAD^{tree}")
        state: dict[str, Any] = {
            "reviewed_tree": head.strip() if head else EMPTY_TREE,
            "findings": [],
            "reviewed_for": "",
        }
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
    """Changed files since the last review, their size, and the risky ones."""
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
    if current is None or current == reviewed:
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
    "Run it as: python3 .claude/alpha/hooks/review.py brief, from the root of an "
    "alpha project (one with docs/principles.toml)."
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


def _principle_line(p: dict[str, Any]) -> str:
    line = f"- {p.get('id')} ({p.get('title')}): {p.get('statement')}"
    comps = ", ".join(str(c) for c in p.get("components", []))
    line += f" [components: {comps}]"
    params: dict[str, Any] = p.get("params", {}) or {}
    if params:
        line += " [params: " + ", ".join(f"{k}={v}" for k, v in params.items()) + "]"
    if p.get("override_decision"):
        line += f" [override: {p['override_decision']}]"
    return line


def _diff(root: Path, old: str, new: str) -> list[str]:
    out = _git(root, "diff", "--no-renames", old, new) or ""
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
    current = snapshot(root) or reviewed
    stats = _numstat(root, reviewed, current)
    files = [path for _, path in stats]
    records, _warnings = _common.decision_index(root)
    lines = [f"Tree: {current}", f"Reviewed: {reviewed}", "", "## Principles", ""]
    lines += [_principle_line(p) for p in _relevant_principles(principles, files)]
    lines += ["", "## Decisions", ""]
    lines += [
        f"- {n:04d} {title} ({path})"
        for n, title, status, path in records
        if status == "accepted"
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
    lines += ["", "## Diff", "", *_diff(root, reviewed, current)]
    return "\n".join(lines) + "\n"


def main() -> None:
    _common.check_python()
    root = _common.project_root({})
    if sys.argv[1:] != ["brief"] or not (root / "docs" / "principles.toml").is_file():
        print(USAGE, file=sys.stderr)
        sys.exit(1)
    print(brief(root), end="")


if __name__ == "__main__":
    main()
