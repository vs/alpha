"""Adopting an existing repo (spec §5b): the survey of what's already there."""

import json
import posixpath
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

from alpha import VERSION
from alpha.answers import (
    PHASES,
    PROJECT_JSON,
    Answers,
    AnswersError,
    Condition,
    Step,
    answers_snapshot,
    describe_condition,
    load_answers,
    parse_answers,
    write_answers,
)
from alpha.baseline import accepts, find_record
from alpha.defaults import Source, load_defaults, load_survey
from alpha.generate import copied_files, render_project, source_info, write_json
from alpha.gitops import HOOKS_PATH, UPDATE_STATE, commit_group
from alpha.merge import Change, classify, merge_json, union_lines
from alpha.recipes import RecipeBook, matches
from alpha.records import record_paths, taken_numbers
from alpha.registry import load_registry
from alpha.render.docs import CHAINED_COMMIT_MSG
from alpha.update import UpdatePlan, apply_update
from alpha.validate import area_of

CAP = 50  # entries per list; the rest are counted
SUBJECTS = 50  # recent commits checked against the convention
HOOK_MANAGERS = "hook_managers"


class AdoptError(Exception):
    """The repo can't be adopted as it is; the message says what to do."""


def _git(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args], cwd=target, capture_output=True, text=True
        )
    except OSError as e:
        raise AdoptError(f"Cannot run git ({e}). Install git, then retry.") from e


def _out(target: Path, *args: str) -> str | None:
    done = _git(target, *args)
    return done.stdout.strip() if done.returncode == 0 else None


def _refuse_alpha(target: Path) -> None:
    path = target / PROJECT_JSON
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(data, dict) and "manifest" in data:
        raise AdoptError(
            f"alpha already generated or adopted {target} ({PROJECT_JSON} has a "
            "manifest). Change it with /alpha:extend instead."
        )


def _repo(target: Path) -> None:
    top = _out(target, "rev-parse", "--show-toplevel")
    if top is None:
        raise AdoptError(
            f"{target} isn't a git repository. alpha adopts a repo's committed "
            "code: run git init, commit the code, then retry."
        )
    if Path(top).resolve() != target.resolve():
        raise AdoptError(
            f"{target} is inside the repository at {top}. Adopt the repository "
            f"from its root: run this on {top}."
        )
    if _out(target, "rev-parse", "--verify", "--quiet", "HEAD") is None:
        raise AdoptError(
            f"{target} has no commits yet. Commit the code first, then retry."
        )


def _capped(items: list[str], key: str, into: dict[str, Any]) -> None:
    into[key] = items[:CAP]
    if len(items) > CAP:
        into[f"{key}_more"] = len(items) - CAP


def _default_branch(target: Path, branch: str) -> str:
    origin = _out(target, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    if origin:
        return origin.removeprefix("refs/remotes/origin/")
    for name in ("main", "master"):
        if _out(target, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
            return name
    return branch


def _dirty(target: Path) -> list[str]:
    # Unstripped: each entry starts with its status column, often a space.
    fields = _git(target, "status", "--porcelain", "-z", "-unormal").stdout.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if not entry:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":  # a rename or copy: its source path comes next
            i += 1
    return paths


def _conventional(target: Path, types: list[str]) -> dict[str, Any]:
    log = _out(target, "log", f"-{SUBJECTS}", "--format=%s") or ""
    subjects = [s for s in log.splitlines() if s]
    pattern = re.compile(rf"^({'|'.join(map(re.escape, types))})(\([^)]+\))?!?: \S")
    others = [s for s in subjects if not pattern.match(s)]
    return {
        "checked": len(subjects),
        "matching": len(subjects) - len(others),
        "others": others[:5],
    }


def _git_facts(target: Path, defaults: dict[str, Any]) -> dict[str, Any]:
    branch = _out(target, "rev-parse", "--abbrev-ref", "HEAD") or ""
    dirty = _dirty(target)
    facts: dict[str, Any] = {
        "head": _out(target, "rev-parse", "HEAD") or "",
        "branch": branch,
        "default_branch": _default_branch(target, branch),
        "clean": not dirty,
    }
    _capped(sorted(dirty), "dirty", facts)
    facts["commits"] = int(_out(target, "rev-list", "--count", "HEAD") or "0")
    facts["conventional"] = _conventional(target, list(defaults["git"]["types"]))
    facts["hooks_path"] = _out(target, "config", "--get", "core.hooksPath") or ""
    return facts


def _tracked(target: Path) -> list[str]:
    done = _git(target, "ls-files", "-z")
    if done.returncode != 0:
        raise AdoptError(f"git ls-files failed in {target}: {done.stderr.strip()}")
    return sorted(p for p in done.stdout.split("\0") if p)


def _inside(path: str, folder: str) -> str | None:
    """`path` relative to `folder`, or None when it's outside."""
    if folder == ".":
        return path
    return path[len(folder) + 1 :] if path.startswith(f"{folder}/") else None


def _components(files: list[str], book: RecipeBook) -> list[dict[str, Any]]:
    stacks = sorted({*book.kit_stacks(), *book.drafted})
    found: dict[tuple[str, str], list[str]] = {}
    for stack in stacks:
        markers = set(book.get(stack).detect)
        for path in files:
            if posixpath.basename(path) in markers:
                folder = posixpath.dirname(path) or "."
                found.setdefault((folder, stack), []).append(path)
    folders = {folder for folder, _ in found}
    out: list[dict[str, Any]] = []
    for (folder, stack), marked in sorted(found.items()):
        recipe = book.get(stack)
        nested = [f for f in folders if f != folder and _inside(f, folder)]
        sources = tests = 0
        for path in files:
            rel = _inside(path, folder)
            if rel is None or any(_inside(path, n) is not None for n in nested):
                continue
            if matches(rel, recipe.exclude_globs):
                continue
            if matches(rel, recipe.test_globs):
                tests += 1
            elif matches(rel, recipe.source_globs):
                sources += 1
        out.append(
            {
                "path": folder,
                "stack": stack,
                "markers": sorted(marked),
                "sources": sources,
                "tests": tests,
            }
        )
    return out


def survey(
    target: Path, source: Source, book: RecipeBook | None = None
) -> dict[str, Any]:
    """What the repo already has, in facts (spec §5b, step 1)."""
    _refuse_alpha(target)
    _repo(target)
    files = _tracked(target)
    globs = load_survey(source)
    git = _git_facts(target, load_defaults(source))
    managers = [p for p in files if matches(p, globs.get(HOOK_MANAGERS, []))]
    _capped(managers, HOOK_MANAGERS, git)
    listed: dict[str, Any] = {}
    for key, patterns in globs.items():
        if key != HOOK_MANAGERS:
            _capped([p for p in files if matches(p, patterns)], key, listed)
    return {
        "git": git,
        "components": _components(files, book or RecipeBook()),
        "files": listed,
        "tracked": len(files),
    }


def saved_adoption(target: Path) -> dict[str, Any]:
    """The `adoption` object project.json holds now, or an empty one."""
    try:
        data: object = json.loads((target / PROJECT_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    adoption: object = cast(dict[str, Any], data).get("adoption", {})
    return cast(dict[str, Any], adoption) if isinstance(adoption, dict) else {}


# --- installing alpha onto the repo (spec §5b, step 5) ---

ADOPT_BRANCH = "alpha/adopt"
GITIGNORE = ".gitignore"
SETTINGS = ".claude/settings.json"


@dataclass(frozen=True)
class AdoptionPlan:
    update: UpdatePlan
    notes: tuple[str, ...]  # what the settings merge kept of the repo's
    copies: dict[str, Path]  # copied files, whose mode is kept


def _answers(target: Path) -> dict[str, Any]:
    path = target / PROJECT_JSON
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise AdoptError(
            f"{target} has no interview answers ({PROJECT_JSON}). Run /alpha:adopt "
            "to survey the repo and settle every area first."
        ) from None
    except ValueError as e:
        raise AdoptError(
            f"Fix {PROJECT_JSON}: it can't be read as JSON ({e})."
        ) from None
    if not isinstance(data, dict):
        raise AdoptError(f"Fix {PROJECT_JSON}: it isn't a JSON object.")
    top = cast(dict[str, Any], data)
    if "adoption" not in top:
        raise AdoptError(
            f"{PROJECT_JSON} is a new project's interview, not an adoption. Run "
            "/alpha:new-project to generate it in an empty folder, or start the "
            "adoption over with /alpha:adopt."
        )
    hooks: object = cast(dict[str, Any], top["adoption"]).get("git_hooks")
    if hooks is None:
        raise AdoptError(
            'Fix project.json: adoption.git_hooks is missing. Set it to "alpha" '
            "(alpha runs git's hooks) or \"chain\" (the repo's hook manager runs "
            "alpha's commit-msg check)."
        )
    return top


def _uncommitted(target: Path) -> list[str]:
    status = _git(target, "status", "--porcelain", "-z", "-uall").stdout
    paths: list[str] = []
    fields = status.split("\0")
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if not entry:
            continue
        if entry[0] in "RC":
            i += 1
        if entry[3:] not in (PROJECT_JSON, ".claude/settings.local.json"):
            paths.append(entry[3:])
    return paths


def _change(path: str, after: str, disk: str | None, notes: list[str]) -> Change | None:
    if disk is not None and disk != after:
        if path == GITIGNORE:
            return Change(path, "merge", union_lines(disk, after))
        if path == SETTINGS:
            merged = merge_json(disk, after)
            if merged is not None:
                notes += [f"{SETTINGS}: {note}" for note in merged[1]]
                return Change(path, "merge", merged[0])
    return classify(path, None, after, disk)


def plan_adoption(
    target: Path, plugin_root: Path, source: Source, today: date
) -> AdoptionPlan:
    _refuse_alpha(target)
    _repo(target)
    top = _answers(target)
    try:
        a = parse_answers(top, target)
    except AnswersError as e:
        area = area_of(e.where)
        if area:
            raise AdoptError(f"Revisit the {area} area: {e}") from None
        raise AdoptError(f"Fix {PROJECT_JSON}: {e}") from None
    dirty = _uncommitted(target)
    if dirty:
        raise AdoptError(
            f"Commit or stash your changes first ({', '.join(dirty[:5])}): alpha "
            "installs onto the committed code, on a branch of its own."
        )
    records = record_paths(a, taken=taken_numbers(target))
    added = {c.name: today for c in a.components}
    rendered = render_project(
        target,
        a,
        load_defaults(source),
        today.year,
        today,
        records,
        added,
        registry=load_registry(source),
    )
    copies = copied_files(plugin_root)
    texts = dict(rendered.texts)
    for rel, src in copies.items():
        if rel in texts:
            raise AdoptError(f"{rel} is both rendered and copied; report this bug.")
        texts[rel] = src.read_text(encoding="utf-8")
    notes: list[str] = []
    changes: list[Change] = []
    for path in sorted(texts):
        disk_path = target / path
        disk = disk_path.read_text(encoding="utf-8") if disk_path.is_file() else None
        change = _change(path, texts[path], disk, notes)
        if change is not None and change.text != disk:
            changes.append(change)
    writes = [
        c.path for c in changes if c.kind in ("new", "change", "merge", "conflict")
    ]
    manifest = {
        "kit_version": VERSION,
        "generated_at": today.isoformat(),
        "adopted_at": today.isoformat(),
        "defaults": source_info(source),
        "applied": answers_snapshot(top),
        "records": records.to_json(),
        "added": {name: day.isoformat() for name, day in added.items()},
    }
    plan = UpdatePlan(
        changes=tuple(changes),
        new_components=(),  # adopted components are the app: never committed whole
        groups={p: commit_group(p, rendered.component_of) for p in writes},
        manifest=manifest,
        answers=top,
    )
    return AdoptionPlan(plan, tuple(notes), copies)


def _branch(target: Path) -> str:
    branch = _out(target, "rev-parse", "--abbrev-ref", "HEAD") or ""
    if branch != _default_branch(target, branch):
        return branch
    if _out(target, "rev-parse", "--verify", "--quiet", f"refs/heads/{ADOPT_BRANCH}"):
        raise AdoptError(
            f"A branch {ADOPT_BRANCH} already exists. Switch to it (git switch "
            f"{ADOPT_BRANCH}) to go on with that adoption, or delete it, then retry."
        )
    done = _git(target, "switch", "--quiet", "-c", ADOPT_BRANCH)
    if done.returncode != 0:
        raise AdoptError(
            f"git couldn't create {ADOPT_BRANCH}: {done.stderr.strip()}. Fix that, "
            "then retry."
        )
    return ADOPT_BRANCH


def apply_adoption(target: Path, adoption: AdoptionPlan) -> list[str]:
    branch = _branch(target)
    apply_update(target, adoption.update)
    for rel, src in adoption.copies.items():
        path = target / rel
        if path.is_file() and any(
            c.path == rel and c.kind == "new" for c in adoption.update.changes
        ):
            path.chmod(src.stat().st_mode & 0o777)
    state_path = target / UPDATE_STATE
    state = json.loads(state_path.read_text(encoding="utf-8"))
    write_json(state_path, {**state, "kind": "adopt"})
    notes = [f"On branch {branch}.", *adoption.notes]
    adopting = cast(dict[str, Any], adoption.update.answers["adoption"])
    if adopting.get("git_hooks") == "alpha":
        done = _git(target, "config", "core.hooksPath", HOOKS_PATH)
        if done.returncode != 0:
            raise AdoptError(
                f"git couldn't set core.hooksPath: {done.stderr.strip()}. Run git "
                f"config core.hooksPath {HOOKS_PATH} yourself."
            )
    else:
        notes.append(
            "Your hook manager stays in charge of git's hooks: its commit-msg hook "
            f"must call {CHAINED_COMMIT_MSG} (CONTRIBUTING.md says so too)."
        )
    return notes


# --- the compliance plan (spec §5b, step 6) ---

_CHECK_STEPS = ("lint", "typecheck", "test")
_TITLES = {
    "lint": "Add a linter",
    "typecheck": "Add a type checker",
    "test": "Add a test runner",
}


def _principles_for(defaults: dict[str, Any], kind: str) -> list[str]:
    table = cast(dict[str, list[str]], defaults.get("adopt", {}).get("principles", {}))
    return list(table.get(kind, []))


def _gap(
    sid: str,
    phase: str,
    title: str,
    why: str,
    principles: list[str],
    acceptance: list[dict[str, Any]],
    component: str | None = None,
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    step: dict[str, Any] = {"id": sid, "phase": phase, "title": title, "why": why}
    if component is not None:
        step["component"] = component
    step["principles"] = principles
    if depends_on:
        step["depends_on"] = depends_on
    step["acceptance"] = acceptance
    step["status"] = "pending"
    return step


def gaps(a: Answers, defaults: dict[str, Any]) -> list[dict[str, Any]]:
    """The mechanical steps the answers call for, in phase order (spec §5b)."""
    found: list[dict[str, Any]] = []
    if a.git_hooks == "chain":
        found.append(
            _gap(
                "p0-chain-commit-hook",
                "P0",
                "Run alpha's commit check from the repo's hook manager",
                "The repo's own hook manager runs git's hooks, so the commit "
                "convention binds nobody until its commit-msg hook calls "
                f"`{CHAINED_COMMIT_MSG}`.",
                _principles_for(defaults, "chain"),
                [{"commit_hook": True}],
            )
        )
    threshold = (
        a.testing.diff_coverage
        if a.testing is not None and a.testing.diff_coverage is not None
        else int(defaults.get("testing", {}).get("diff_coverage", 0))
    )
    book = a.book()
    formatted: set[str] = set()
    for c in a.components:
        recipe = book.get(c.stack)
        if not recipe.adopted:
            continue
        check = {"run": f"mise run check:component:{c.name}"}
        if not recipe.commands.get("format_check"):
            formatted.add(c.name)
            found.append(
                _gap(
                    f"p1-format-{c.name}",
                    "P1",
                    f"Format {c.name} in one commit",
                    f"{c.name}'s code isn't formatted yet, so its format check is "
                    "off. Format it in a commit of its own, list that commit in "
                    ".git-blame-ignore-revs, and turn the check on in its recipe.",
                    _principles_for(defaults, "format"),
                    [{"recipe": f"{c.name}.commands.format_check"}, check],
                    c.name,
                )
            )
        for step in _CHECK_STEPS:
            if not recipe.commands.get(step):
                found.append(
                    _gap(
                        f"p2-{step}-{c.name}",
                        "P2",
                        f"{_TITLES[step]} for {c.name}",
                        f"Nothing runs a {step} check on {c.name}. Add the tool, "
                        "set it in the recipe, and baseline its legacy findings.",
                        _principles_for(defaults, step),
                        [{"recipe": f"{c.name}.commands.{step}"}, check],
                        c.name,
                    )
                )
        if not recipe.coverage and threshold > 0:
            found.append(
                _gap(
                    f"p2-coverage-{c.name}",
                    "P2",
                    f"Measure coverage of {c.name}'s changed lines",
                    f"Pull requests must cover {threshold}% of the lines they "
                    f"change, but {c.name}'s recipe has no coverage command.",
                    _principles_for(defaults, "coverage"),
                    [{"recipe": f"{c.name}.coverage"}],
                    c.name,
                )
            )
    for check in a.baselines:
        kind, _, name = check.partition(":")
        component = name or None
        first = f"p1-format-{name}" if name in formatted else None
        found.append(
            _gap(
                f"p5-baseline-{check.replace(':', '-')}",
                "P5",
                f"Clear the {check} baseline",
                f"Legacy {check} findings are baselined (alpha baseline show). Fix "
                f"them, risk paths first, then remove {check} from "
                "adoption.baselines so the check runs plain again.",
                _principles_for(defaults, kind if name else check),
                [{"no_baseline": check}],
                component,
                [first] if first else None,
            )
        )
    return sorted(found, key=lambda s: s["phase"])  # stable: keeps list order


def merge_steps(
    existing: list[dict[str, Any]], found: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """`existing` as it is, then each found step it doesn't have yet."""
    have = {str(s.get("id")) for s in existing}
    return [*existing, *(s for s in found if s["id"] not in have)]


RUN_TIMEOUT = 600  # seconds, as the ratchet's
_FINISHED = ("done", "dropped")


def _ordered(steps: tuple[Step, ...]) -> list[Step]:
    return sorted(steps, key=lambda s: PHASES.index(s.phase))  # stable


def next_step(a: Answers) -> tuple[Step | None, str]:
    """The next ready step, or None and why none is. A step depends only on
    steps listed before it, so while any is unfinished, one is ready."""
    finished = {s.id for s in a.steps if s.status in _FINISHED}
    for s in _ordered(a.steps):
        if s.id not in finished and set(s.depends_on) <= finished:
            return s, ""
    if not a.steps:
        return None, "The plan has no steps: run alpha adopt gaps --save first."
    return None, "Every step of the adoption plan is done or dropped."


def describe_step(s: Step) -> str:
    lines = [f"{s.id} ({s.phase}): {s.title}", f"Why: {s.why}", "Done when:"]
    lines += [f"  - {describe_condition(c)}" for c in s.acceptance]
    lines.append(f"Branch: {s.branch or 'alpha/' + s.id}")
    return "\n".join(lines)


def _hook_runs_alpha(target: Path, a: Answers) -> bool:
    if a.git_hooks != "chain":
        return _out(target, "config", "core.hooksPath") == HOOKS_PATH
    hooks = Path(_out(target, "rev-parse", "--git-path", "hooks") or ".git/hooks")
    hook = (hooks if hooks.is_absolute() else target / hooks) / "commit-msg"
    try:
        return f"{HOOKS_PATH}/commit-msg" in hook.read_text(encoding="utf-8")
    except OSError:
        return False


def _problem(c: Condition, target: Path, a: Answers, confirmed: bool) -> str | None:
    """Why the condition doesn't hold, or None when it does."""
    if c.kind == "run":
        try:
            done = subprocess.run(
                c.value,
                shell=True,
                cwd=target / c.dir,
                capture_output=True,
                text=True,
                timeout=RUN_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return f"`{c.value}` took longer than {RUN_TIMEOUT}s"
        except OSError as e:
            return f"`{c.value}` can't run in {c.dir} ({e})"
        if done.returncode == 0:
            return None
        tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-20:])
        return f"`{c.value}` failed (exit {done.returncode}):\n{tail}"
    if c.kind == "recipe":
        name, _, field_ = c.value.partition(".")
        comp = next((x for x in a.components if x.name == name), None)
        if comp is None:
            return f"there's no component {name}"
        recipe = a.book().get(comp.stack)
        group, _, step = field_.partition(".")
        if field_ == "coverage":
            value = recipe.coverage
        else:
            value = recipe.commands.get(step, "") if group == "commands" else ""
        return None if value else f"{comp.stack}'s {field_} is still empty"
    if c.kind == "no_baseline":
        return (
            f"{c.value} is still in adoption.baselines"
            if c.value in a.baselines
            else None
        )
    if c.kind == "commit_hook":
        if _hook_runs_alpha(target, a):
            return None
        return (
            "git's commit-msg hook doesn't run alpha's commit check yet: add "
            f"`{CHAINED_COMMIT_MSG}` to it"
        )
    if confirmed:
        return None
    return (
        f"needs the user's confirmation that {c.value}. Ask them, then rerun with "
        "--confirmed-by-user"
    )


def _load_steps(target: Path) -> tuple[Answers, dict[str, Any], list[dict[str, Any]]]:
    try:
        a = load_answers(target / PROJECT_JSON)
    except AnswersError as e:
        raise AdoptError(f"Fix {PROJECT_JSON}: {e}") from None
    saved = saved_adoption(target)
    return (
        a,
        saved,
        [dict(s) for s in cast(list[dict[str, Any]], saved.get("steps", []))],
    )


def _step(a: Answers, sid: str) -> Step:
    found = next((s for s in a.steps if s.id == sid), None)
    if found is None:
        ids = ", ".join(s.id for s in a.steps) or "none"
        raise AdoptError(f"No step {sid!r} in adoption.steps (steps: {ids}).")
    return found


def _save_step(
    target: Path,
    saved: dict[str, Any],
    raw: list[dict[str, Any]],
    sid: str,
    **fields: Any,
) -> None:
    for entry in raw:
        if entry.get("id") == sid:
            entry.update(fields)
    write_answers(target, json.dumps({"adoption": {**saved, "steps": raw}}))


def start(target: Path, sid: str) -> Step:
    a, saved, raw = _load_steps(target)
    s = _step(a, sid)
    if s.status in _FINISHED:
        raise AdoptError(f"{sid} is already {s.status}.")
    branch = s.branch or f"alpha/{sid}"
    _save_step(target, saved, raw, sid, status="in_progress", branch=branch)
    return _step(_load_steps(target)[0], sid)


def done(target: Path, sid: str, confirmed: bool = False) -> list[str]:
    """Check every condition; mark the step done only when all hold. Raises
    AdoptError listing the ones that don't."""
    a, saved, raw = _load_steps(target)
    s = _step(a, sid)
    report: list[str] = []
    failed = False
    for c in s.acceptance:
        problem = _problem(c, target, a, confirmed)
        failed = failed or problem is not None
        mark = "ok  " if problem is None else "FAIL"
        report.append(f"{mark} {describe_condition(c)}")
        if problem is not None:
            report.append(f"     {problem}")
    if failed:
        raise AdoptError(f"{sid} isn't done yet:\n" + "\n".join(report))
    _save_step(target, saved, raw, sid, status="done")
    return report


def drop(target: Path, sid: str, decision: str) -> None:
    a, saved, raw = _load_steps(target)
    _step(a, sid)
    record = find_record(target, decision)
    if record is None:
        raise AdoptError(
            f"No decision record {decision} in docs/decisions/. Dropping a step "
            "loosens the plan, so record why with the user first (the project's "
            "/decision skill), then pass its number."
        )
    if not accepts(record, sid):
        rel = record.relative_to(target).as_posix()
        raise AdoptError(
            f"{rel} doesn't drop {sid}: it needs `Status: accepted` and the step id "
            f"in backticks (`{sid}`), with why the step isn't needed."
        )
    _save_step(target, saved, raw, sid, status="dropped", decision=int(decision))
