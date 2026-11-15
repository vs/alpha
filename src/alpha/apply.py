"""Write alpha's files into a folder: a new project, an adoption, or an update.

All three are one operation (spec of the rewrite, "Writing files"): render
the answers with this kit, merge each file three ways (alpha's last render,
the file on disk, the new render), and write. A new project and an adoption
have no base; an update's base is the render alpha last committed
(alpha.rendered). alpha's own files (hooks, checks, the git hook, the copied
agents and skills) are always replaced, never proposed for a hand merge.
"""

import difflib
import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, cast

from alpha import VERSION, adopt
from alpha.answers import PROJECT_JSON, area_of, parse_answers, write_json
from alpha.defaults import Source, load_defaults
from alpha.generate import (
    PRINCIPLES_TOML,
    GenerateError,
    Rendered,
    copied_files,
    render_project,
)
from alpha.gitops import (
    HOOKS_PATH,
    PROPOSALS,
    UPDATE_STATE,
    commit_group,
    digest,
    git_init,
    set_hooks_path,
    status_paths,
)
from alpha.merge import Change, classify, merge_settings, union_lines
from alpha.registry import load_registry
from alpha.rendered import Base, find_base, write_tree
from alpha.validate import AnswersError

GITIGNORE = ".gitignore"
SETTINGS = ".claude/settings.json"
# Folders whose every file is alpha's own: one the kit no longer ships goes.
OWNED_DIRS = (
    ".claude/alpha/hooks/",
    ".claude/alpha/checks/",
    ".claude/alpha/githooks/",
)
# alpha's own files outside those folders that an older kit shipped.
RETIRED = (".claude/skills/debt/SKILL.md",)
# Files a new project's folder may hold before alpha writes into it.
_NEW_FOLDER_FILES = frozenset({PROJECT_JSON, ".claude/settings.local.json"})
_NEW_FOLDER_DIRS = frozenset({".claude", ".claude/alpha"})
_WRITES = ("new", "change", "merge", "conflict")
_ORDER = ("new", "change", "merge", "conflict", "deleted", "stale", "skipped")
_NOTES = {
    "merge": " (your edits kept)",
    "conflict": " (your edits overlap alpha's change: merge by hand)",
    "deleted": " (alpha no longer ships it)",
    "stale": " (alpha no longer generates it: delete it if you don't need it)",
    "skipped": " (you deleted it: alpha's change to it is left out)",
}


@dataclass(frozen=True)
class Plan:
    mode: str  # "new", "adopt" or "update"
    changes: tuple[Change, ...]
    texts: Mapping[str, str]  # the whole render, kept as the next base
    executable: frozenset[str]
    new_components: tuple[str, ...]
    groups: dict[str, str]
    answers: dict[str, Any]  # project.json, `installed` included
    notes: tuple[str, ...] = ()
    upgraded_from: str | None = None
    git_hooks: str = "alpha"


def _read(path: Path) -> str | None:
    return path.read_bytes().decode("utf-8") if path.is_file() else None


def _project_json(target: Path) -> dict[str, Any]:
    path = target / PROJECT_JSON
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GenerateError(
            f"{target} has no alpha answers ({PROJECT_JSON}). Run /alpha:install "
            "there first."
        ) from None
    except (OSError, ValueError) as e:
        raise GenerateError(
            f"Fix {PROJECT_JSON}: it can't be read as JSON ({e})."
        ) from None
    if not isinstance(data, dict):
        raise GenerateError(f"Fix {PROJECT_JSON}: it isn't a JSON object.")
    top = cast(dict[str, Any], data)
    if "manifest" in top and "installed" not in top:
        raise GenerateError(
            f"An older alpha set {target} up (its {PROJECT_JSON} has a manifest). "
            "This alpha doesn't upgrade it on its own: follow the by-hand steps in "
            "alpha's README (Projects an older alpha set up), then run alpha apply."
        )
    return top


def _mode(top: Mapping[str, Any]) -> str:
    if "installed" in top:
        return "update"
    return "adopt" if "adoption" in top else "new"


def _extra_files(target: Path, license_file: str | None) -> list[str]:
    """What a new project's folder holds besides what an interview leaves."""
    found: list[str] = []

    def walk(folder: Path) -> None:
        for entry in folder.iterdir():
            rel = entry.relative_to(target).as_posix()
            if entry.name == ".DS_Store" or rel in (".git", ".claude/alpha/state"):
                continue
            if rel in _NEW_FOLDER_DIRS and entry.is_dir() and not entry.is_symlink():
                walk(entry)
            elif rel not in _NEW_FOLDER_FILES and rel != license_file:
                found.append(rel)

    walk(target)
    return sorted(found)


def _version(text: object) -> tuple[int, ...] | None:
    if not isinstance(text, str):
        return None
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        return None


def _installed(top: Mapping[str, Any]) -> dict[str, Any]:
    raw: object = top.get("installed", {})
    return cast(dict[str, Any], raw) if isinstance(raw, dict) else {}


def _upgraded_from(target: Path, installed: Mapping[str, Any]) -> str | None:
    old: object = installed.get("kit_version")
    was, now = _version(old), _version(VERSION)
    if was is None or now is None or was == now:
        return None
    if was > now:
        raise GenerateError(
            f"{target} was set up by alpha {old}, newer than this alpha ({VERSION}). "
            "Update alpha (claude plugin update alpha@alpha), then retry."
        )
    return cast(str, old)


def _dates(
    installed: Mapping[str, Any], names: list[str], today: date
) -> dict[str, date]:
    raw: object = installed.get("components", {})
    known = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
    out: dict[str, date] = {}
    for name in names:
        day = known.get(name)
        try:
            out[name] = date.fromisoformat(day) if isinstance(day, str) else today
        except ValueError:
            out[name] = today
    return out


def _base_components(base: Base | None) -> dict[str, dict[str, Any]]:
    """The components alpha's last render had, by name, from its principles."""
    if base is None or PRINCIPLES_TOML not in base.texts:
        return {}
    try:
        data = tomllib.loads(base.texts[PRINCIPLES_TOML])
    except tomllib.TOMLDecodeError:
        return {}
    comps: object = data.get("components", [])
    items = cast(list[object], comps) if isinstance(comps, list) else []
    return {
        str(c["name"]): c
        for c in (cast(dict[str, Any], i) for i in items if isinstance(i, dict))
        if "name" in c
    }


def _moves(
    target: Path,
    before: Mapping[str, dict[str, Any]],
    after: Rendered,
    a_paths: Mapping[str, str],
) -> dict[str, tuple[str, str]]:
    """The components whose folder moved since the last render. alpha doesn't
    move app code, so their files must already be in the new folder."""
    moves: dict[str, tuple[str, str]] = {}
    for name, path in a_paths.items():
        old = before.get(name, {}).get("path")
        if not isinstance(old, str) or old == path:
            continue
        theirs = [p for p, n in after.component_of.items() if n == name]
        there = (
            all((target / p).is_file() for p in theirs)
            if theirs
            else (target / path).is_dir()
        )
        if not there:
            raise GenerateError(
                f"The {name} component moves from {old} to {path}. alpha doesn't move "
                "app code: move its files yourself (git mv), commit, then run this "
                "again."
            )
        moves[name] = (old, path)
    return moves


def _written_as(
    path: str, after: Rendered, moves: Mapping[str, tuple[str, str]]
) -> str:
    """Where alpha wrote `path` before: its old place when its component moved."""
    name = after.component_of.get(path)
    if name is None or name not in moves:
        return path
    old, new = moves[name]
    return (PurePosixPath(old) / PurePosixPath(path).relative_to(new)).as_posix()


def _moved_lockfiles(
    target: Path, before: Mapping[str, dict[str, Any]], after: Rendered
) -> list[str]:
    """A note for each lockfile on disk the components stop using: the package
    manager wrote it, so deleting it is the user's."""
    now = {c["name"]: c for c in after.principles["components"]}
    used = {lock for c in now.values() for lock in c["lockfiles"]}
    notes: list[str] = []
    for name, c in before.items():
        for lock in cast(list[str], c.get("lockfiles", [])):
            if name not in now or lock in used or not (target / lock).is_file():
                continue
            new = ", ".join(now[name]["lockfiles"])
            notes.append(
                f"{'stale':<10}{lock} ({name} now locks its dependencies in {new}: "
                f"delete this file and the build output beside it; "
                f"`{now[name]['commands']['setup']}` writes {new})"
                if new
                else f"{'stale':<10}{lock} ({name} has no lockfile any more: delete it)"
            )
    return notes


def _owned_on_disk(target: Path) -> list[str]:
    found: list[str] = [p for p in RETIRED if (target / p).is_file()]
    for folder in OWNED_DIRS:
        root = target / folder
        if root.is_dir():
            found += [
                p.relative_to(target).as_posix()
                for p in root.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts
            ]
    return found


def _change(
    path: str,
    before: str | None,
    after: str | None,
    disk: str | None,
    owned: bool,
    notes: list[str],
) -> Change | None:
    if owned:
        if after is None:
            return Change(path, "deleted", None) if disk is not None else None
        if disk == after:
            return None
        return Change(path, "new" if disk is None else "change", after)
    if after is not None and disk is not None and path == SETTINGS:
        merged = merge_settings(disk, after, before)
        if merged is not None:
            text, kept = merged
            notes += [f"{SETTINGS}: {note}" for note in kept]
            return None if text == disk else Change(path, "merge", text)
    if after is not None and disk is not None and before is None and path == GITIGNORE:
        text = union_lines(disk, after)
        return None if text == disk else Change(path, "merge", text)
    return classify(path, before, after, disk)


def plan(target: Path, plugin_root: Path, source: Source, today: date) -> Plan:
    """What `write` would change, and why. Writes nothing."""
    if not target.is_dir():
        raise GenerateError(
            f"{target} is not a folder. Create it, then run /alpha:install."
        )
    top = _project_json(target)
    mode = _mode(top)
    if (target / UPDATE_STATE).exists():
        raise GenerateError(
            "An update is waiting to be committed. Merge any proposals in "
            f"{PROPOSALS}/, run alpha commit {target}, then run this again."
        )
    installed = _installed(top)
    upgraded_from = _upgraded_from(target, installed)
    base = find_base(target) if mode == "update" else None
    before_comps = _base_components(base)
    raw_known: object = installed.get("components", {})
    known = cast(dict[str, object], raw_known) if isinstance(raw_known, dict) else {}
    try:
        # A scoped override may outlive its component; it then applies to nothing.
        a = parse_answers(top, target, former={*before_comps, *known})
    except AnswersError as e:
        area = area_of(e.where)
        raise GenerateError(
            f"Revisit the {area} area: {e}" if area else f"Fix {PROJECT_JSON}: {e}"
        ) from None
    if mode == "new":
        license_file = a.identity.license_file if a.identity else None
        extra = _extra_files(target, license_file)
        if extra:
            raise GenerateError(
                f"{target} is not empty (found: {', '.join(extra)}). A new project "
                "starts in an empty folder; /alpha:install adopts an existing repo "
                "instead (commit its files first)."
            )
    if mode == "adopt":
        adopt.check_adoptable(target, top)
    names = [c.name for c in a.components]
    dates = _dates(installed, names, today)
    on = installed.get("on")
    year = date.fromisoformat(on).year if isinstance(on, str) else today.year
    registry = load_registry(source)
    after = render_project(
        target, a, load_defaults(source), year, today, dates, registry=registry
    )
    copies = copied_files(plugin_root)
    texts: dict[str, str] = dict(after.texts)
    for rel, src in copies.items():
        if rel in texts or rel in after.component_of:
            raise GenerateError(
                f"{rel} is both rendered and copied by the kit. Report this bug."
            )
        texts[rel] = src.read_text(encoding="utf-8")
    executable = frozenset(
        rel for rel, src in copies.items() if src.stat().st_mode & 0o111
    )
    preexisting: list[str]
    if mode == "adopt":
        preexisting = sorted(rel for rel in texts if (target / rel).exists())
    else:
        raw: object = installed.get("preexisting", [])
        preexisting = (
            [str(p) for p in cast(list[object], raw)] if isinstance(raw, list) else []
        )
    keep = set(preexisting)
    moves = _moves(target, before_comps, after, {c.name: c.path for c in a.components})
    notes: list[str] = []
    changes: list[Change] = []
    owned = set(copies)
    on_disk = set(_owned_on_disk(target))
    paths: list[str] = sorted(set(texts) | set(base.texts if base else ()) | on_disk)
    for path in paths:
        is_owned = (
            path in owned or path.startswith(OWNED_DIRS) or path in RETIRED
        ) and path not in keep
        before = base.texts.get(_written_as(path, after, moves)) if base else None
        disk = _read(target / path)
        change = _change(path, before, texts.get(path), disk, is_owned, notes)
        if change is not None and (change.text is None or change.text != disk):
            changes.append(change)
    touched = [c.path for c in changes if c.kind in (*_WRITES, "deleted")]
    if mode != "new" and touched:
        dirty = status_paths(target, *touched, command="apply")
        if dirty:
            raise GenerateError(
                f"Commit or stash your changes to {', '.join(dirty)} first: alpha "
                "merges its changes into the committed files."
            )
    new_components = tuple(
        c.name
        for c in a.components
        if c.name not in before_comps
        and (mode != "adopt" or c.name in adopt.new_components(target, a))
    )
    if mode == "update":
        for c in a.components:
            if c.name in new_components and c.path != ".":
                theirs = status_paths(target, c.path, command="update")
                if theirs:
                    raise GenerateError(
                        f"Commit or move your files in {c.path}/ first "
                        f"({', '.join(theirs[:5])}), then run alpha update "
                        f"{target} again."
                    )
    answers = {
        **top,
        "installed": {
            "kit_version": VERSION,
            "mode": installed.get("mode", "adopted" if mode == "adopt" else "new"),
            "on": on if isinstance(on, str) else today.isoformat(),
            "components": {
                **{str(k): v for k, v in known.items()},
                **{name: day.isoformat() for name, day in dates.items()},
            },
            "preexisting": preexisting,
        },
    }
    return Plan(
        mode=mode,
        changes=tuple(changes),
        texts=texts,
        executable=executable,
        new_components=new_components,
        groups={p: commit_group(p, after.component_of) for p in touched},
        answers=answers,
        notes=tuple(notes + _moved_lockfiles(target, before_comps, after)),
        upgraded_from=upgraded_from,
        git_hooks=a.git_hooks or "alpha",
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def write(target: Path, p: Plan) -> list[str]:
    """Write the plan; returns notes for the user."""
    notes: list[str] = []
    if p.mode == "new":
        git_init(target)
    if p.mode == "adopt":
        notes.append(f"On branch {adopt.switch_branch(target)}.")
    for c in p.changes:
        path = target / c.path
        if c.kind == "deleted":
            path.unlink(missing_ok=True)
        elif c.kind == "conflict" and c.text is not None:
            _write(target / PROPOSALS / c.path, c.text)
        elif c.kind in _WRITES and c.text is not None:
            _write(path, c.text)
            if c.path in p.executable:
                path.chmod(0o755)
    tree = write_tree(target, p.texts, set(p.executable))
    write_json(target / PROJECT_JSON, p.answers)
    if p.mode in ("new", "adopt"):
        if p.git_hooks == "alpha":
            set_hooks_path(target)
        else:
            notes.append(
                "Your hook manager stays in charge of git's hooks: its commit-msg "
                f'hook must call `sh {HOOKS_PATH}/commit-msg "$1"`, between '
                "`# alpha:begin` and `# alpha:end` lines."
            )
    write_json(
        target / UPDATE_STATE,
        {
            "kind": p.mode,
            "groups": p.groups,
            "new_components": list(p.new_components),
            "conflicts": {
                c.path: digest((target / c.path).read_bytes())
                for c in p.changes
                if c.kind == "conflict" and (target / c.path).is_file()
            },
            "render_tree": tree,
        },
    )
    for c in p.changes:
        if c.kind == "conflict":
            notes.append(f"{c.path}: merge by hand; proposal: {PROPOSALS}/{c.path}")
    return notes


def describe(p: Plan, target: Path, bootstrap_flags: str = "") -> str:
    count = sum(c.kind in (*_WRITES, "deleted") for c in p.changes)
    if not p.changes and not p.new_components and p.mode == "update":
        return "alpha update: nothing to change"
    verb = {"new": "alpha apply", "adopt": "alpha apply (adoption)"}.get(
        p.mode, "alpha update"
    )
    kit = f" (kit {p.upgraded_from} to {VERSION})" if p.upgraded_from else ""
    lines = [f"{verb}{kit}: {count} file{'' if count == 1 else 's'} to change"]
    for c in sorted(p.changes, key=lambda c: (_ORDER.index(c.kind), c.path)):
        lines.append(f"  {c.kind:<10}{c.path}{_NOTES.get(c.kind, '')}")
    lines += [f"  {note}" for note in p.notes]
    if p.new_components:
        flags = bootstrap_flags or " ".join(
            f"--component {n}" for n in p.new_components
        )
        lines.append(
            f"New components: {', '.join(p.new_components)}. Then run: "
            f"alpha bootstrap {target} {flags}"
        )
    return "\n".join(lines)


def plan_diff(p: Plan, target: Path) -> str:
    out: list[str] = []
    for c in p.changes:
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
