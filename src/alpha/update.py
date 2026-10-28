"""Merge a change in the answers into a project alpha generated (spec §5a).

The project is rendered twice with this kit: from the answers it was
generated from ("before") and from the current answers ("after"). Only the
difference between the two lands, merged into the files on disk, so the
user's edits stay and kit changes since generation cancel out.
"""

import difflib
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, cast

from alpha.answers import PROJECT_JSON, Answers, answers_snapshot, parse_answers
from alpha.defaults import Source, load_defaults
from alpha.generate import (
    GenerateError,
    Rendered,
    file_hashes,
    render_project,
    write_json,
)
from alpha.gitops import PROPOSALS, UPDATE_STATE, commit_group
from alpha.merge import Change, classify
from alpha.records import Records, record_paths, taken_numbers
from alpha.validate import AnswersError, area_of

_WRITES = ("new", "change", "merge", "conflict")  # what the count and git cover
_ORDER = ("new", "change", "merge", "conflict", "stale", "skipped")
REVIEW = ".claude/alpha/hooks/review.py"
REVIEW_NOTE = "The reviewer will look at alpha's changes at the next Stop."
_NOTES = {
    "merge": " (your edits kept)",
    "conflict": " (your edits overlap alpha's change: merge by hand)",
    "stale": " (alpha no longer generates it: delete it if you don't need it)",
    "skipped": " (you deleted it: alpha's change to it is left out)",
}


@dataclass(frozen=True)
class UpdatePlan:
    changes: tuple[Change, ...]  # sorted by path
    new_components: tuple[str, ...]
    groups: dict[str, str]  # changed path -> its commit group
    manifest: dict[str, Any]  # the manifest to write
    answers: dict[str, Any]  # the full current file


def _read(path: Path) -> str | None:
    """The file's text exactly as stored, or None when there is no file."""
    if not path.is_file():
        return None
    return path.read_bytes().decode("utf-8")


def _not_kept(target: Path) -> GenerateError:
    return GenerateError(
        f"{target} was generated before alpha kept the answers it generated "
        "from, so alpha can't tell your edits from its own changes. Updating it "
        "isn't supported."
    )


def _baseline(
    target: Path, manifest: dict[str, Any]
) -> tuple[Records, dict[str, date], int]:
    """The records, component dates and generation year the manifest keeps."""
    records = Records.from_json(manifest.get("records"))
    raw: object = manifest.get("added")
    if records is None or not isinstance(raw, dict):
        raise _not_kept(target)
    try:
        added = {
            str(name): date.fromisoformat(cast(str, day))
            for name, day in cast(dict[object, object], raw).items()
        }
        year = date.fromisoformat(cast(str, manifest.get("generated_at"))).year
    except (TypeError, ValueError):
        raise _not_kept(target) from None
    return records, added, year


def _load(target: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """The answers file and its manifest (steps 1-3)."""
    path = target / PROJECT_JSON
    if not path.is_file():
        raise GenerateError(
            f"{target} has no alpha answers, so alpha didn't generate it. alpha "
            "changes only projects it generated; bringing an existing project in "
            "is out of scope for this version."
        )
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise GenerateError(
            f"Fix {PROJECT_JSON}: it can't be read as JSON ({e})."
        ) from None
    if not isinstance(data, dict):
        raise GenerateError(f"Fix {PROJECT_JSON}: it isn't a JSON object.")
    top = cast(dict[str, Any], data)
    manifest: object = top.get("manifest")
    if not isinstance(manifest, dict):
        raise GenerateError(
            f"{target} isn't generated yet. Finish the interview with "
            "/alpha:new-project."
        )
    manifest = cast(dict[str, Any], manifest)
    if not isinstance(manifest.get("applied"), dict):
        raise _not_kept(target)
    return top, manifest


def _check_history(applied: dict[str, Any], current: dict[str, Any]) -> None:
    for key in ("decisions", "overrides"):
        now: object = current.get(key, [])
        now_list = cast(list[object], now) if isinstance(now, list) else []
        for i, entry in enumerate(cast(list[object], applied.get(key, []))):
            if i >= len(now_list) or now_list[i] != entry:
                raise GenerateError(
                    f"{key}[{i}] changed since the project was generated. Decision "
                    "records are history: put it back as it was, and add a new "
                    "decision for the change instead."
                )


def _moves(target: Path, before: Answers, after: Answers) -> dict[str, tuple[str, str]]:
    """Components whose folder changed, by name: (old path, new path)."""
    old = {c.name: c.path for c in before.components}
    moves: dict[str, tuple[str, str]] = {}
    for c in after.components:
        if c.name not in old or old[c.name] == c.path:
            continue
        manifests = after.book().get(c.stack).manifests
        if not all((target / c.path / m).is_file() for m in manifests):
            raise GenerateError(
                f"The {c.name} component moves from {old[c.name]} to {c.path}. "
                "alpha doesn't move app code: move its files yourself (git mv), "
                "commit, then run this again."
            )
        moves[c.name] = (old[c.name], c.path)
    return moves


def _before_text(
    path: str, before: Rendered, after: Rendered, moves: dict[str, tuple[str, str]]
) -> str | None:
    """What "before" had for an "after" path: a moved template is under its old path."""
    name = after.component_of.get(path)
    if name in moves:
        old, new = moves[name]
        rel = PurePosixPath(path).relative_to(new)
        return before.texts.get((PurePosixPath(old) / rel).as_posix())
    return before.texts.get(path)


def _dirty(target: Path, paths: list[str]) -> list[str]:
    """The paths git sees changes to; refuses a folder that isn't a repository."""
    try:
        done = subprocess.run(
            ["git", "status", "--porcelain", "-z", "-uall", "--", *paths],
            cwd=target,
            capture_output=True,
            text=True,
        )
    except OSError as e:
        raise GenerateError(
            f"Cannot run git ({e}). Install git, then rerun the update."
        ) from e
    if done.returncode != 0:
        raise GenerateError(
            f"{target} isn't a git repository ({done.stderr.strip()}), so alpha "
            "can't tell your uncommitted edits from the generated files. Commit "
            "the project to git first, then run this again."
        )
    fields = done.stdout.split("\0")
    seen: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if not entry:
            continue
        seen.append(entry[3:])
        if entry[0] in "RC":  # a rename or copy: its source path comes next
            i += 1
    return seen


def plan_update(target: Path, source: Source, today: date) -> UpdatePlan:
    """Work out what the change in the answers does to each file; write nothing."""
    top, manifest = _load(target)
    records, added, year = _baseline(target, manifest)
    if (target / UPDATE_STATE).exists():
        raise GenerateError(
            "An update is waiting to be committed. Merge any proposals in "
            f"{PROPOSALS}/, run alpha commit-update {target}, then run alpha "
            "update again."
        )
    applied = cast(dict[str, Any], manifest["applied"])
    defaults = load_defaults(source)
    try:
        was = parse_answers(applied, target, generated=True)
        before = render_project(target, was, defaults, year, today, records, added)
    except (AnswersError, GenerateError, ValueError, KeyError) as e:
        raise GenerateError(
            f"The answers {target} was generated from don't load with this alpha "
            f"({e}). Updating a project generated by an older alpha isn't "
            "supported yet."
        ) from None
    try:
        now = parse_answers(top, target)
    except AnswersError as e:
        area = area_of(e.where)
        if area:
            raise GenerateError(f"Revisit the {area} area: {e}") from None
        raise GenerateError(f"Fix {PROJECT_JSON}: {e}") from None
    _check_history(applied, top)
    moves = _moves(target, was, now)

    new_records = record_paths(now, known=records, taken=taken_numbers(target))
    dates = {c.name: added.get(c.name, today) for c in now.components}
    after = render_project(target, now, defaults, year, today, new_records, dates)
    changes: list[Change] = []
    for path in sorted({*before.texts, *after.texts}):
        disk = _read(target / path)
        change = classify(
            path, _before_text(path, before, after, moves), after.texts.get(path), disk
        )
        # A merge equal to the disk: the user already made alpha's change.
        if change is not None and (change.text is None or change.text != disk):
            changes.append(change)
    touched = [c.path for c in changes if c.kind in _WRITES]
    dirty = _dirty(target, touched) if touched else []
    if dirty:
        raise GenerateError(
            f"Commit or stash your changes to {', '.join(dirty)} first: alpha "
            "merges its changes into the committed files."
        )
    old_names = {c.name for c in was.components}
    for c in now.components:
        if c.name in old_names or c.path == ".":
            continue
        # Its folder is committed in alpha's build commit: the user's files
        # there would go in with it.
        theirs = _dirty(target, [c.path])
        if theirs:
            raise GenerateError(
                f"Commit or move your files in {c.path}/ first "
                f"({', '.join(theirs[:5])}), then run alpha update {target} again."
            )
    return UpdatePlan(
        changes=tuple(changes),
        new_components=tuple(c.name for c in now.components if c.name not in old_names),
        groups={p: commit_group(p, after.component_of) for p in touched},
        manifest={
            **manifest,
            "applied": answers_snapshot(top),
            "records": new_records.to_json(),
            "added": {name: day.isoformat() for name, day in dates.items()},
            "updated_at": today.isoformat(),
        },
        answers=top,
    )


def _review_hook(target: Path, *args: str) -> str | None:
    """Run the project's review hook on target; its output, or None if it failed."""
    script = target / REVIEW
    if not script.is_file():
        return None
    try:
        done = subprocess.run(
            ["python3", str(script), *args],
            cwd=target,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def _review_snapshot(target: Path) -> str | None:
    """The review hook's tree id of the working tree, or None without one."""
    return (_review_hook(target, "snapshot") or "").strip() or None


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def apply_update(target: Path, plan: UpdatePlan) -> list[str]:
    """Write alpha's side of each change; overlapping ones go to proposals.
    Returns notes for the user.

    Only this run's proposals are written: one kept from an earlier update is
    still the only copy of a change the user hasn't merged."""
    before_tree = _review_snapshot(target)
    for c in plan.changes:
        if c.text is None:
            continue
        if c.kind == "conflict":
            _write(target / PROPOSALS / c.path, c.text)
        elif c.kind in _WRITES:
            _write(target / c.path, c.text)
    manifest = dict(plan.manifest)
    old: object = manifest.get("files")
    kept = list(cast(dict[str, object], old)) if isinstance(old, dict) else []
    rels = sorted({*kept, *(c.path for c in plan.changes)})
    manifest["files"] = file_hashes(target, [r for r in rels if (target / r).is_file()])
    write_json(target / PROJECT_JSON, {**plan.answers, "manifest": manifest})
    conflicts = {
        c.path: hashlib.sha256((target / c.path).read_bytes()).hexdigest()
        for c in plan.changes
        if c.kind == "conflict"
    }
    after_tree = _review_snapshot(target)  # every write is in, project.json too
    # alpha's writes aren't Claude's: tell the review hook now, since a Stop can
    # come before commit-update.
    carried = (
        before_tree is not None
        and after_tree is not None
        and _review_hook(target, "absorb", before_tree, after_tree) is not None
    )
    state = target / UPDATE_STATE
    state.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        state,
        {
            "before_tree": before_tree,
            "after_tree": after_tree,
            "groups": plan.groups,
            "new_components": list(plan.new_components),
            "conflicts": conflicts,
        },
    )
    return [] if carried else [REVIEW_NOTE]


def describe(plan: UpdatePlan, target: Path) -> str:
    """One line per change, then how to bootstrap any new component."""
    count = sum(c.kind in _WRITES for c in plan.changes)
    if not plan.changes and not plan.new_components:
        return "alpha update: nothing to change"
    lines = [f"alpha update: {count} file{'' if count == 1 else 's'} to change"]
    for c in sorted(plan.changes, key=lambda c: (_ORDER.index(c.kind), c.path)):
        lines.append(f"  {c.kind:<10}{c.path}{_NOTES.get(c.kind, '')}")
    if plan.new_components:
        flags = " ".join(f"--component {n}" for n in plan.new_components)
        lines.append(
            f"New components: {', '.join(plan.new_components)}. Then run: "
            f"alpha bootstrap {target} {flags}"
        )
    return "\n".join(lines)


def plan_diff(plan: UpdatePlan, target: Path) -> str:
    """A unified diff, disk to new text, of each file the update writes."""
    out: list[str] = []
    for c in plan.changes:
        if c.kind not in ("new", "change", "merge") or c.text is None:
            continue
        disk = _read(target / c.path) or ""
        out += difflib.unified_diff(
            disk.splitlines(keepends=True),
            c.text.splitlines(keepends=True),
            f"a/{c.path}",
            f"b/{c.path}",
        )
    return "".join(out)
