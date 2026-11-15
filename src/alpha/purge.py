"""alpha purge: alpha out of a project, in one commit (rewrite spec, R3).

Everything is planned in memory first: the files to delete, and for each kept
file alpha wrote an edit that removes only what points at alpha. The result is
scanned, and a kept file that still names a removed path stops purge before
anything is written. Then purge switches the hooks off, writes, drops alpha's
git refs and commits exactly the paths it changed.
"""

import dataclasses
import json
import re
import shutil
import subprocess
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

from alpha import apply, rendered, toml_write
from alpha.answers import Answers, parse_answers
from alpha.defaults import Source, load_defaults
from alpha.generate import (
    GenerateError,
    copied_files,
    load_project_principles,
    project_book,
)
from alpha.gitops import status_paths
from alpha.hooks_wiring import commit_msg_hook, marked_block, uninstall
from alpha.merge import strip_alpha_hooks
from alpha.principles import build_principles
from alpha.registry import load_registry
from alpha.render.claude_settings import render_settings
from alpha.repo_checks import repo_checks
from alpha.shell import GIT_TIMEOUT
from alpha.status import SETTINGS, read_answers

REMOVED_DIRS = (".claude/alpha/", "docs/alpha/")
MARKDOWN = ("CLAUDE.md", "CONTRIBUTING.md", "README.md")
TOOL_CONFIGS = ("_typos.toml", ".rumdl.toml", "lychee.toml")
MISE = "mise.toml"
GITIGNORE = ".gitignore"
WORKFLOWS = ".github/workflows/"
REVIEW_NOTES = "refs/notes/alpha-review"
RATCHET = re.compile(
    r"python3 (?:\.\./)*\.claude/alpha/checks/ratchet\.py ([\w:.-]+)"
    r"( --coverage| --file \{file\})?"
)
_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6}) ")


@dataclass(frozen=True)
class Removed:
    """What purge takes away, for telling which lines point at it."""

    paths: frozenset[str]
    skills: tuple[str, ...]
    agents: tuple[str, ...]

    def named_in(self, text: str) -> bool:
        flat = text.replace("\\", "")  # a regex in a tool config escapes its dots
        if "/alpha:" in flat or any(d in flat for d in REMOVED_DIRS):
            return True
        if any(p in flat for p in self.paths):
            return True
        for skill in self.skills:
            if re.search(rf"\b{re.escape(skill)} skill\b", flat) or re.search(
                rf"(?<![\w/.-])/{re.escape(skill)}\b", flat
            ):
                return True
        return any(
            re.search(rf"\b{re.escape(agent)} agent\b", flat)
            or ("-" in agent and re.search(rf"\b{re.escape(agent)}\b", flat))
            for agent in self.agents
        )


class Uncleanable(GenerateError):
    """A kept file still points at what purge removes."""


# --- pure removers, one per kind of kept file ---


def _fenced(lines: list[str]) -> list[bool]:
    inside = False
    flags: list[bool] = []
    for line in lines:
        if _FENCE.match(line):
            flags.append(True)
            inside = not inside
        else:
            flags.append(inside)
    return flags


def _without_empty_fences(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if (
            _FENCE.match(line)
            and out
            and _FENCE.match(out[-1])
            and line.strip()
            in (
                "```",
                "~~~",
            )
        ):
            out.pop()
            continue
        out.append(line)
    return out


def _without_empty_headings(lines: list[str]) -> list[str]:
    while True:
        fenced = _fenced(lines)
        heads = [
            (i, len(m.group(1)))
            for i, line in enumerate(lines)
            if not fenced[i] and (m := _HEADING.match(line))
        ]
        level_at = dict(heads)
        empty = None
        for i, level in heads:
            j = next((k for k in range(i + 1, len(lines)) if lines[k].strip()), None)
            if j is None or (j in level_at and level_at[j] <= level):
                empty = i
                break
        if empty is None:
            return lines
        lines = lines[:empty] + lines[empty + 1 :]


def _squeezed(lines: list[str]) -> str:
    out: list[str] = []
    for line in lines:
        if not line.strip() and (not out or not out[-1].strip()):
            continue
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out) + "\n"


def clean_markdown(text: str, removed: Removed, checks: tuple[str, ...] = ()) -> str:
    """Lines that name alpha, table rows of removed `checks`, and the code
    blocks and headings left empty, out of a Markdown file."""
    rows = tuple(f"| {c} |" for c in checks)
    lines = [
        line
        for line in text.splitlines()
        if not removed.named_in(line) and not line.startswith(rows or ("\0",))
    ]
    return _squeezed(_without_empty_headings(_without_empty_fences(lines)))


def clean_lines(text: str, removed: Removed) -> str:
    """Lines that name alpha out of a file of independent lines (.gitignore)."""
    kept = [
        line for line in text.splitlines(keepends=True) if not removed.named_in(line)
    ]
    return "".join(kept)


def _clean_array_line(line: str, keep: Callable[[str], bool]) -> str:
    """A one-line `key = [...]` with the entries `keep` rejects taken out; the
    line as it was when it isn't one."""
    try:
        data = tomllib.loads(line)
    except tomllib.TOMLDecodeError:
        return line
    if len(data) != 1:
        return line
    key, value = next(iter(data.items()))
    if not isinstance(value, list):
        return line
    items = cast(list[object], value)
    kept = [v for v in items if not isinstance(v, str) or keep(v)]
    return line if kept == items else toml_write.dumps({key: kept})


def clean_toml_arrays(text: str, removed: Removed) -> str:
    """Array entries naming alpha out of a tool config's one-line arrays."""
    return "".join(
        _clean_array_line(line, lambda v: not removed.named_in(v))
        if removed.named_in(line)
        else line
        for line in text.splitlines(keepends=True)
    )


def unratcheted(text: str, plain: Mapping[str, str], where: str) -> str:
    """Each command that ran through alpha's ratchet, back to the plain one."""
    problems: list[str] = []

    def swap(match: re.Match[str]) -> str:
        key = match.group(1) + (match.group(2) or "")
        command = plain.get(key)
        if command is None or any(c in command for c in "\"'\\"):
            problems.append(match.group(0))
            return match.group(0)
        return command

    out = RATCHET.sub(swap, text)
    if problems:
        raise Uncleanable(
            f"{where}: alpha can't put {problems[0]} back to the plain command. "
            "Replace it with the command it checks by hand, then rerun alpha purge."
        )
    return out


def _task_name(header: str) -> str | None:
    match = re.match(r'^\[tasks\.(?:"([^"]+)"|([\w:-]+))\]\s*$', header)
    return (match.group(1) or match.group(2)) if match else None


def clean_mise(text: str, removed: Removed) -> tuple[str, list[str]]:
    """mise.toml without the tasks whose `run` names alpha, nor their names in
    any `depends`; returns the text and the removed task names."""
    blocks: list[list[str]] = [[]]
    for line in text.splitlines(keepends=True):
        if line.startswith("[") and blocks[-1]:
            blocks.append([])
        blocks[-1].append(line)
    gone: list[str] = []
    kept: list[list[str]] = []
    for block in blocks:
        name = _task_name(block[0]) if block else None
        if name is not None:
            try:
                task = tomllib.loads("".join(block[1:]))
            except tomllib.TOMLDecodeError:
                task = {}
            run: object = task.get("run", "")
            runs = cast(list[object], run) if isinstance(run, list) else [run]
            if any(removed.named_in(str(r)) for r in runs):
                gone.append(name)
                continue
        kept.append(block)
    lines = [line for block in kept for line in block]
    out = "".join(
        _clean_array_line(line, lambda v: v not in gone)
        if line.lstrip().startswith("depends")
        else line
        for line in lines
    )
    return out, gone


def clean_workflow(text: str, gone_tasks: list[str]) -> str:
    """A CI workflow without the steps that run a removed mise task."""
    if not gone_tasks:
        return text
    runs = re.compile(
        r"mise run (?:--\S+ )*(?:"
        + "|".join(map(re.escape, gone_tasks))
        + r")(?![\w:-])"
    )
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        step = re.match(r"^(\s*)- ", lines[i])
        if step is None:
            out.append(lines[i])
            i += 1
            continue
        indent = len(step.group(1))
        j = i + 1
        while j < len(lines):
            rest = lines[j]
            depth = len(rest) - len(rest.lstrip())
            if rest.strip() and depth <= indent:
                break
            j += 1
        block = lines[i:j]
        if not any(runs.search(line) for line in block):
            out += block
        i = j
    return "".join(out)


def clean_settings(
    settings: dict[str, object], alpha_permissions: Mapping[str, list[str]]
) -> dict[str, object]:
    """settings.json without alpha's hook entries and permission rules, and
    without a table left empty."""
    out = dict(settings)
    if "hooks" in out:
        hooks = strip_alpha_hooks(out["hooks"])
        if hooks:
            out["hooks"] = hooks
        else:
            del out["hooks"]
    perms: object = out.get("permissions")
    if isinstance(perms, dict):
        kept: dict[str, object] = {}
        for kind, rules in cast(dict[str, object], perms).items():
            if not isinstance(rules, list):
                kept[kind] = rules
                continue
            left = [
                r
                for r in cast(list[object], rules)
                if r not in alpha_permissions.get(kind, [])
            ]
            if left:
                kept[kind] = left
        if kept:
            out["permissions"] = kept
        else:
            del out["permissions"]
    return out


def leftovers(rel: str, text: str, removed: Removed) -> list[str]:
    """`file:line` of each line in a kept file that names a removed path."""
    flat = Removed(removed.paths, (), ())
    return [
        f"{rel}:{n}"
        for n, line in enumerate(text.splitlines(), 1)
        if flat.named_in(line)
    ]


# --- the plan ---


@dataclass(frozen=True)
class Purge:
    deletions: tuple[str, ...]  # tracked paths
    edits: Mapping[str, str]
    gone_checks: tuple[str, ...]  # mise tasks removed, as check ids
    plain_checks: tuple[str, ...]  # checks that ran through the ratchet
    subject: str


def _git(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=target,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GenerateError(
            f"git {args[0]} didn't finish in {target} ({e}). Run it yourself to see "
            "why, then rerun alpha purge."
        ) from None


def _tracked(target: Path) -> list[str]:
    done = _git(target, "ls-files", "-z")
    if done.returncode != 0:
        raise GenerateError(
            f"git ls-files failed in {target} ({done.stderr.strip()}). Fix that, "
            "then rerun alpha purge."
        )
    return [p for p in done.stdout.split("\0") if p]


def _plain_commands(
    target: Path, top: dict[str, Any], source: Source
) -> dict[str, str]:
    """Each baselined check, with --coverage or --file {file} for those forms,
    mapped to the command it runs without the ratchet."""
    raw: object = cast(dict[str, Any], top.get("installed", {})).get("components", {})
    former: set[str] = (
        set(cast(dict[str, object], raw)) if isinstance(raw, dict) else set()
    )
    a: Answers = parse_answers(top, target, former=former)
    if not a.baselines:
        return {}
    plain = dataclasses.replace(a, baselines=())
    registry = load_registry(source)
    principles = build_principles(
        load_defaults(source), plain, "purge", registry=registry
    )
    by_name = {c["name"]: c for c in principles["components"]}
    stacks = {c.name: c.stack for c in a.components}
    runs = {c.id: c.command for c in repo_checks(plain, principles, registry)}
    out: dict[str, str] = {}
    for check in a.baselines:
        step, _, name = check.partition(":")
        if not name:
            out[check] = runs[check]
            continue
        commands = by_name[name]["commands"]
        out[check] = commands[step]
        if commands.get("lint_file"):
            out[check + " --file {file}"] = commands["lint_file"]
        coverage = a.book().get(stacks[name]).coverage
        if coverage:
            out[check + " --coverage"] = coverage
    return out


def plan(target: Path, plugin_root: Path, source: Source, today: date) -> Purge:
    top = read_answers(target)
    if top is None or "installed" not in top:
        raise GenerateError(
            f"alpha isn't installed in {target}, so there is nothing to purge."
        )
    render = apply.plan(target, plugin_root, source, today)
    raw_pre: object = cast(dict[str, Any], top["installed"]).get("preexisting", [])
    preexisting: set[str] = (
        {str(p) for p in cast(list[object], raw_pre)}
        if isinstance(raw_pre, list)
        else set()
    )
    copied = [
        rel
        for rel in copied_files(plugin_root)
        if rel.startswith((".claude/agents/", ".claude/skills/"))
    ]
    tracked = _tracked(target)
    deletions = [
        p
        for p in tracked
        if (p.startswith(REMOVED_DIRS) or p in copied) and p not in preexisting
    ]
    removed = Removed(
        frozenset(deletions),
        tuple(
            sorted({p.split("/")[2] for p in copied if p.startswith(".claude/skills/")})
        ),
        tuple(
            sorted({Path(p).stem for p in copied if p.startswith(".claude/agents/")})
        ),
    )
    plain = _plain_commands(target, top, source)
    principles = load_project_principles(target)
    edits: dict[str, str] = {}

    def read(rel: str) -> str | None:
        path = target / rel
        return path.read_text(encoding="utf-8") if path.is_file() else None

    gone: list[str] = []
    text = read(MISE)
    if text is not None:
        edits[MISE], gone = clean_mise(unratcheted(text, plain, MISE), removed)
    checks = tuple(t.removeprefix("check:") for t in gone)
    for rel in MARKDOWN:
        text = read(rel)
        if text is not None:
            edits[rel] = clean_markdown(
                text, removed, checks if rel == "CONTRIBUTING.md" else ()
            )
    for rel in TOOL_CONFIGS:
        text = read(rel)
        if text is not None:
            edits[rel] = clean_toml_arrays(text, removed)
    text = read(GITIGNORE)
    if text is not None:
        edits[GITIGNORE] = clean_lines(text, removed)
    for rel in tracked:
        if rel.startswith(WORKFLOWS) and rel.endswith((".yml", ".yaml")):
            text = read(rel)
            if text is not None:
                edits[rel] = clean_workflow(unratcheted(text, plain, rel), gone)
    text = read(SETTINGS)
    if text is not None:
        try:
            settings: object = json.loads(text)
        except ValueError:
            settings = None
        if not isinstance(settings, dict):
            raise Uncleanable(
                f"{SETTINGS} isn't a JSON object, so alpha can't take its entries "
                "out. Fix its JSON, then rerun alpha purge."
            )
        perms = cast(
            dict[str, list[str]],
            render_settings(principles, project_book(target))["permissions"],
        )
        cleaned = clean_settings(cast(dict[str, object], settings), perms)
        if cleaned or SETTINGS in preexisting:
            edits[SETTINGS] = json.dumps(cleaned, indent=2) + "\n"
        elif SETTINGS in tracked:
            deletions.append(SETTINGS)
    chain = _chain_edit(target, top)
    if chain is not None:
        edits[chain[0]] = chain[1]
    edits = {
        rel: new for rel, new in edits.items() if rel in tracked and new != read(rel)
    }
    problems = [
        found
        for rel in sorted(set(render.texts) | set(edits))
        if rel not in deletions and not rel.startswith(REMOVED_DIRS)
        for found in leftovers(
            rel, edits[rel] if rel in edits else (read(rel) or ""), removed
        )
    ]
    if problems:
        raise Uncleanable(
            "alpha can't take out every pointer to what purge removes, so it wrote "
            f"nothing. Remove these lines by hand, then rerun alpha purge: "
            f"{', '.join(problems)}"
        )
    git = cast(dict[str, Any], principles.get("git", {}))
    conventional = git.get("convention", "conventional") == "conventional"
    return Purge(
        tuple(sorted(deletions)),
        edits,
        checks,
        tuple(sorted(check for check in plain if " " not in check)),
        "chore: Remove alpha" if conventional else "Remove alpha",
    )


def _chain_edit(target: Path, top: dict[str, Any]) -> tuple[str, str] | None:
    """The hook manager's commit-msg file without alpha's marked call."""
    adoption: object = top.get("adoption")
    if not (
        isinstance(adoption, dict)
        and cast(dict[str, Any], adoption).get("git_hooks") == "chain"
    ):
        return None
    hook = commit_msg_hook(target)
    if not hook.path.is_file():
        return None
    lines = hook.path.read_text(encoding="utf-8").splitlines(keepends=True)
    block = marked_block(lines)
    if block is None:
        return None
    return hook.rel, "".join(lines[: block[0]] + lines[block[1] + 1 :])


def purge(
    target: Path, plugin_root: Path, source: Source, today: date, trailers: list[str]
) -> tuple[str, list[str]]:
    """Plan, then uninstall, write and commit; returns the commit and notes."""
    p = plan(target, plugin_root, source, today)
    paths = [*p.deletions, *p.edits]
    dirty = status_paths(target, *paths, command="purge", untracked="no")
    if dirty:
        raise GenerateError(
            f"{', '.join(sorted(dirty))} has uncommitted changes, and purge would "
            "edit or delete it. Commit or stash those changes, then rerun alpha "
            "purge."
        )
    notes = uninstall(target)
    for rel, text in p.edits.items():
        (target / rel).write_text(text, encoding="utf-8")
    for rel in p.deletions:
        (target / rel).unlink(missing_ok=True)
        parent = (target / rel).parent
        while parent != target and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    shutil.rmtree(target / ".claude/alpha", ignore_errors=True)  # its local state
    claude = target / ".claude"
    if claude.is_dir() and not any(claude.iterdir()):
        claude.rmdir()
    rendered.forget(target)
    _git(target, "update-ref", "-d", REVIEW_NOTES)
    args = ["commit", "-q", "-m", p.subject]
    for trailer in trailers:
        args += ["--trailer", trailer]
    done = _git(target, *args, "--", *paths)
    if done.returncode != 0:
        raise GenerateError(
            f"git commit failed in {target}: {(done.stderr or done.stdout).strip()}\n"
            "alpha's files are removed but not committed. Fix that, then commit "
            f"them yourself: git commit -m {p.subject!r} -- {' '.join(paths)}"
        )
    head = _git(target, "rev-parse", "HEAD").stdout.strip()
    if p.plain_checks:
        notes.append(
            "These checks ran through alpha's ratchet and now report the legacy "
            f"findings again: {', '.join(p.plain_checks)}."
        )
    if p.gone_checks:
        notes.append(
            "These repository checks ran alpha's scripts and are gone: "
            f"{', '.join(p.gone_checks)}."
        )
    return head, notes
