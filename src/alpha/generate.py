import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

from alpha import VERSION
from alpha.answers import (
    PROJECT_JSON,
    Answers,
    answers_snapshot,
    drafted_recipes,
    load_answers,
    write_json,
)
from alpha.baseline import BaselineError, baseline_file
from alpha.baseline import capture as capture_baseline
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles, render_principles
from alpha.recipes import (
    RecipeBook,
    check_commands,
    render_component,
    render_workspace,
)
from alpha.records import Records, record_paths
from alpha.registry import Registry, default_registry, load_registry
from alpha.render.ci import render_ci, render_dependabot
from alpha.render.claude_settings import render_settings
from alpha.render.docs import render_docs
from alpha.render.tooling import MISE, render_tooling
from alpha.repo_checks import repo_checks
from alpha.shell import run_command

PRINCIPLES_TOML = "docs/principles.toml"
_ALLOWED_FILES = frozenset({PROJECT_JSON, ".claude/settings.local.json"})
_ALLOWED_DIRS = frozenset({".claude", ".claude/alpha"})
_TAIL_LINES = 40
STEP_TIMEOUT = 1800.0  # seconds: an install or a check that runs longer is stuck


class GenerateError(Exception):
    pass


def _unexpected(target: Path) -> list[str]:
    found: list[str] = []

    def walk(folder: Path) -> None:
        for entry in folder.iterdir():
            rel = entry.relative_to(target).as_posix()
            if entry.name == ".DS_Store":
                continue
            if rel in _ALLOWED_DIRS and entry.is_dir() and not entry.is_symlink():
                walk(entry)
            elif rel not in _ALLOWED_FILES or not entry.is_file():
                found.append(rel)

    walk(target)
    return sorted(found)


def _ignored(principles: dict[str, Any], book: RecipeBook) -> list[str]:
    """The .gitignore entries."""
    # Hooks and checks run with python3, which leaves bytecode next to the
    # modules they import (diff_checks.py imports ratchet.py).
    lines = [
        ".claude/alpha/state/",
        ".claude/settings.local.json",
        ".claude/worktrees/",
        ".DS_Store",
        ".claude/alpha/hooks/__pycache__/",
        ".claude/alpha/checks/__pycache__/",
        ".env",
        ".env.*",
        "**/.env",
        "**/.env.*",
        "!.env.example",
    ]
    for c in principles["components"]:
        recipe = book.get(c["stack"])
        entries = recipe.ignores
        if c.get("workspace"):
            assert recipe.workspace is not None  # only its members are marked
            # What the members share is at the repository root, and only there.
            lines += [f"/{entry}" for entry in recipe.workspace.root_ignores]
            entries = recipe.workspace.member_ignores
        for entry in entries:
            # "**/" keeps the any-depth match the unprefixed pattern has.
            lines.append(entry if c["path"] == "." else f"{c['path']}/**/{entry}")
    return list(dict.fromkeys(lines))


def copied_files(plugin_root: Path) -> dict[str, Path]:
    """The files every project gets as they are: hooks, checks, skills, agents."""
    files = plugin_root / "project-files"
    out = {
        f".claude/alpha/hooks/{p.name}": p
        for p in sorted((files / "hooks").glob("*.py"))
    }
    for skill in sorted((files / "skills").glob("*/SKILL.md")):
        out[f".claude/skills/{skill.parent.name}/SKILL.md"] = skill
    out[".claude/agents/committer.md"] = files / "agents/committer.md"
    out[".claude/agents/principles-reviewer.md"] = (
        files / "agents/principles-reviewer.md"
    )
    for script in sorted((files / "checks").glob("*.py")):
        out[f".claude/alpha/checks/{script.name}"] = script
    out[".claude/alpha/githooks/commit-msg"] = files / "githooks/commit-msg"
    return out


def _display_path(path: Path) -> str:
    try:
        return f"~/{path.relative_to(Path.home()).as_posix()}"
    except ValueError:
        return str(path)


def _source_commit(source: Source) -> str | None:
    if not source.checkout:
        return None
    try:
        done = subprocess.run(
            ["git", "-C", str(source.path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def source_info(source: Source) -> dict[str, Any]:
    """Where the kit defaults came from, for the manifest."""
    return {
        "path": _display_path(source.path),
        "live": source.checkout,
        "commit": _source_commit(source),
    }


@dataclass(frozen=True)
class Rendered:
    principles: dict[str, Any]
    texts: dict[str, str]
    component_of: dict[str, str]


def _collision(a: Answers, name: str, rel: str) -> GenerateError:
    stack = next(c.stack for c in a.components if c.name == name)
    return GenerateError(
        f"The {stack} recipe's template {rel} collides with a file alpha "
        "generates. Remove that template from the recipe (alpha writes the "
        "file itself), then retry."
    )


def render_project(
    target: Path,
    a: Answers,
    defaults: dict[str, Any],
    year: int,
    today: date,
    records: Records | None = None,
    added: Mapping[str, date] | None = None,
    *,
    registry: Registry | None = None,
) -> Rendered:
    records = records or record_paths(a)
    registry = registry or default_registry()
    principles = build_principles(defaults, a, VERSION, records, registry=registry)
    book = a.book()
    texts: dict[str, str] = {PRINCIPLES_TOML: render_principles(principles)}
    texts.update(
        render_docs(
            a,
            principles,
            year,
            today,
            root=target,
            records=records,
            added=added,
            registry=registry,
        )
    )
    component_files: dict[str, tuple[str, str]] = {}
    slug = principles["project"]["slug"]
    members = {c["name"] for c in principles["components"] if c.get("workspace")}
    for c in a.components:
        recipe = book.get(c.stack)
        files = render_component(c, slug, recipe, member=c.name in members)
        component_files.update({rel: (text, c.name) for rel, text in files.items()})
    for stack in dict.fromkeys(c.stack for c in a.components if c.name in members):
        shared = [c for c in a.components if c.stack == stack and c.name in members]
        files = render_workspace(book.get(stack), [c.path for c in shared], slug)
        # Named after its first member, for a collision's message.
        component_files.update(
            {rel: (text, shared[0].name) for rel, text in files.items()}
        )
    texts[".claude/settings.json"] = (
        json.dumps(render_settings(principles, book), indent=2) + "\n"
    )
    texts[".gitignore"] = "\n".join(_ignored(principles, book)) + "\n"
    texts.update(
        render_tooling(
            repo_checks(a, principles, registry),
            registry,
            _ignored(principles, book),
            [lock for c in principles["components"] for lock in c["lockfiles"]],
            components=principles["components"],
            ci=a.build is not None and a.build.ci != "none",
        )
    )
    assert a.build is not None
    texts.update(render_ci(principles, a.build.ci, book, registry))
    assert a.dependencies is not None
    cooldown = a.dependencies.cooldown_days
    if cooldown is None:
        cooldown = defaults["dependencies"]["cooldown_days"]
    texts.update(
        render_dependabot(
            principles,
            a.dependencies.updates,
            a.dependencies.schedule,
            a.build.ci,
            book,
            cooldown,
        )
    )
    component_of: dict[str, str] = {}
    for rel, (text, name) in component_files.items():
        if rel in texts:
            raise _collision(a, name, rel)
        texts[rel] = text
        component_of[rel] = name
    return Rendered(principles, texts, component_of)


def generate(
    target: Path,
    plugin_root: Path,
    source: Source,
    year: int,
    today: date | None = None,
) -> list[str]:
    if not target.is_dir():
        raise GenerateError(
            f"{target} is not a folder. Create it and run the alpha interview "
            "there first."
        )
    answers_path = target / PROJECT_JSON
    extra = _unexpected(target)
    a = load_answers(answers_path) if extra and answers_path.is_file() else None
    if a is not None and a.identity is not None:
        extra = [rel for rel in extra if rel != a.identity.license_file]
    if extra:
        raise GenerateError(
            f"{target} is not empty (found: {', '.join(extra)}). alpha v0.1 starts "
            "projects only in empty folders. Choose a new folder, or move these "
            "files out first."
        )
    a = a or load_answers(answers_path)
    records = record_paths(a)
    today = today or date.today()
    rendered = render_project(
        target,
        a,
        load_defaults(source),
        year,
        today,
        records,
        registry=load_registry(source),
    )
    texts = rendered.texts
    copies = copied_files(plugin_root)
    for rel, name in rendered.component_of.items():
        if rel in copies:
            raise _collision(a, name, rel)

    for rel, text in texts.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for rel, src in copies.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, path)  # keeps the exec bit of the git hook

    generated = sorted([*texts, *copies])
    data = cast(dict[str, Any], json.loads(answers_path.read_text(encoding="utf-8")))
    data["manifest"] = {
        "kit_version": VERSION,
        "generated_at": today.isoformat(),
        "defaults": source_info(source),
        "files": file_hashes(target, generated),
        "applied": answers_snapshot(data),
        "records": records.to_json(),
        "added": {c.name: today.isoformat() for c in a.components},
    }
    write_json(answers_path, data)
    return sorted([*generated, PROJECT_JSON])


def digest(data: bytes) -> str:
    """A labelled digest: a bare hex string next to a path like "...-api-keys.md"
    reads as a leaked key to the project's secrets check."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def file_hashes(target: Path, rels: list[str]) -> dict[str, str]:
    return {rel: digest((target / rel).read_bytes()) for rel in rels}


def _project_json(target: Path) -> dict[str, Any] | None:
    """project.json, or None when there is none; an unreadable one stops."""
    path = target / PROJECT_JSON
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        problem: object = e
    else:
        if isinstance(data, dict):
            return cast(dict[str, Any], data)
        problem = "it isn't a JSON object"
    raise GenerateError(
        f"{path} can't be read as the interview answers ({problem}). Restore it "
        f"with git checkout {PROJECT_JSON}, or fix it by hand, then retry."
    )


def refresh_manifest(target: Path) -> None:
    data = _project_json(target)
    manifest: object = data.get("manifest") if data is not None else None
    if data is None or not isinstance(manifest, dict):
        return
    files = cast(dict[str, str], cast(dict[str, Any], manifest).get("files", {}))
    present = [rel for rel in files if (target / rel).is_file()]
    data["manifest"]["files"] = file_hashes(target, present)
    write_json(target / PROJECT_JSON, data)


def load_project_principles(target: Path) -> dict[str, Any]:
    path = target / PRINCIPLES_TOML
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise GenerateError(
            f'{path} not found. Run "alpha generate {target}" first, in a folder '
            "that holds the interview answers."
        ) from None
    except tomllib.TOMLDecodeError as e:
        raise GenerateError(
            f"{path} is not valid TOML ({e}). Fix the syntax, then retry."
        ) from None
    problem = _principles_problem(data)
    if problem:
        raise GenerateError(
            f"{path}: {problem}. Fix it by hand, or restore it with "
            f'"git checkout {PRINCIPLES_TOML}" (or "alpha update {target}"), then '
            "retry."
        )
    return data


def _principles_problem(data: dict[str, Any]) -> str | None:
    """What's wrong with the fields alpha's commands read, or None."""
    project: object = data.get("project")
    if not isinstance(project, dict):
        return "project is missing" if project is None else "project must be a table"
    if not isinstance(cast(dict[str, Any], project).get("slug"), str):
        return "project.slug is missing"
    components: object = data.get("components")
    if components is None:
        return "components is missing"
    if not isinstance(components, list):
        return "components must be a list of [[components]] tables"
    for i, raw in enumerate(cast(list[object], components)):
        if not isinstance(raw, dict):
            return f"components[{i}] must be a [[components]] table"
        c = cast(dict[str, Any], raw)
        name = c.get("name")
        where = (
            f'components[{i}] ("{name}")'
            if isinstance(name, str)
            else (f"components[{i}]")
        )
        for key in ("name", "path", "stack"):
            if key not in c:
                return f"{where}.{key} is missing"
            if not isinstance(c[key], str):
                return f"{where}.{key} must be text"
        commands = c.get("commands")
        if not isinstance(commands, dict):
            return f'{where}.commands must be a table of step = "command"'
        for step in ("setup", "test"):
            if step not in commands:
                return f"{where}.commands.{step} is missing"
        for step, command in cast(dict[str, object], commands).items():
            if not isinstance(command, str):
                return f"{where}.commands.{step} must be text"
        lockfiles = c.get("lockfiles", [])
        if not isinstance(lockfiles, list) or not all(
            isinstance(x, str) for x in cast(list[object], lockfiles)
        ):
            return f"{where}.lockfiles must be a list of paths"
    baselines: object = data.get("baselines", [])
    if not isinstance(baselines, list):
        return "baselines must be a list of [[baselines]] tables"
    for i, raw in enumerate(cast(list[object], baselines)):
        if not isinstance(raw, dict) or not isinstance(
            cast(dict[str, Any], raw).get("id"), str
        ):
            return f"baselines[{i}].id is missing"
    return None


def project_book(target: Path) -> RecipeBook:
    data = _project_json(target)
    if data is None:
        return RecipeBook()
    raw: object = data.get("recipes", {})
    return RecipeBook(drafted_recipes(raw, generated=True))


def _run(label: str, command: str, cwd: Path, fix: str) -> None:
    """Run one bootstrap step, announced on stderr; raise with its output's tail."""
    print(f"alpha: {label}: {command}", file=sys.stderr, flush=True)
    done = run_command(command, cwd, STEP_TIMEOUT)
    if done is None:
        raise GenerateError(
            f'"{command}" took longer than {STEP_TIMEOUT:g}s in {cwd}, so alpha '
            "stopped it. If it waits for input, run it there yourself; otherwise "
            f"find out why it's slow.\n{fix}"
        )
    if done.code != 0:
        tail = "\n".join(done.out.splitlines()[-_TAIL_LINES:])
        raise GenerateError(
            f'"{command}" failed in {cwd} (exit {done.code}). '
            f"Last lines of its output:\n{tail}\n{fix}"
        )


def _require_mise(target: Path) -> None:
    if shutil.which("mise") is None:
        raise GenerateError(
            "mise is not installed. Install it (brew install mise, or "
            "https://mise.jdx.dev/getting-started.html), then rerun "
            f'"alpha bootstrap {target}".'
        )


def _mise_tools(target: Path) -> list[str]:
    """The tools the project's mise.toml pins, as `mise install` names them."""
    path = target / MISE
    try:
        tools: object = tomllib.loads(path.read_text(encoding="utf-8")).get("tools")
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise GenerateError(
            f"{path} can't be read ({e}). Fix it, or restore alpha's version with "
            f'"git checkout {MISE}", then rerun "alpha bootstrap {target}".'
        ) from None
    return list(cast(dict[str, object], tools)) if isinstance(tools, dict) else []


def _capture(target: Path, checks: Sequence[str]) -> None:
    """Record today's findings as the baselines of `checks`, once their tools
    are installed and before their checks run."""
    for check in checks:
        print(f"alpha: baseline: capture {check}", file=sys.stderr, flush=True)
        try:
            print(capture_baseline(target, check), file=sys.stderr, flush=True)
        except BaselineError as e:
            raise GenerateError(
                f"Capturing the {check} baseline failed:\n{e}\nFix that, then "
                f'rerun "alpha bootstrap {target} --capture-baselines".'
            ) from None


def _repo_checks(target: Path, capture: Sequence[str] = ()) -> None:
    """Install the repository checks' tools and run the ones CI runs on a PR."""
    _require_mise(target)
    if not (target / ".git").exists():
        # jactionlint and the secrets check need a repository; commit-skeleton
        # then keeps this one.
        try:
            done = subprocess.run(
                ["git", "init", "-q", "-b", "main"],
                cwd=target,
                capture_output=True,
                text=True,
            )
            problem = done.stderr.strip() if done.returncode else ""
        except OSError as e:
            problem = str(e)
        if problem:
            raise GenerateError(
                f"git init failed in {target}: {problem}\nThe repository checks "
                f'need a git repository. Fix that, then rerun "alpha bootstrap '
                f'{target}".'
            )
    rerun = f'rerun "alpha bootstrap {target}"'
    label = "repository checks"
    _run(
        label,
        "mise trust --yes",
        target,
        f"Fix what mise reports about {target / MISE}, then {rerun}",
    )
    # Only the project's tools: a bare `mise install` also installs everything
    # in the user's global config, and would blame its failures on the checks.
    tools = _mise_tools(target)
    if tools:
        install = shlex.join(["mise", "install", *tools])
        _run(
            label,
            install,
            target,
            f'Check your network, or run "{install}" in {target} to see which '
            f"tool failed, then {rerun}",
        )
    _capture(target, capture)
    _run(
        label,
        "mise run --continue-on-error ci",  # report every failing check
        target,
        "Fix what the repository checks report (mise run check:<id> reruns one) "
        f"and {rerun}",
    )


def bootstrap(
    target: Path,
    principles: dict[str, Any],
    only: Sequence[str] = (),
    capture_baselines: bool = False,
) -> None:
    """`capture_baselines`: record each listed baseline that's missing, once
    its tools are installed (spec §8b); otherwise a missing one stops here."""
    fix = (
        "Fix the failing step (is the component's toolchain installed?) and rerun "
        f'"alpha bootstrap {target}"'
    )
    known = [c["name"] for c in principles["components"]]
    for name in only:
        if name not in known:
            raise GenerateError(
                f"No component named {name} in {PRINCIPLES_TOML} "
                f"(components: {', '.join(known)})."
            )
    uncaptured = [
        str(e["id"])
        for e in principles.get("baselines", [])
        if not baseline_file(target, str(e["id"])).is_file()
    ]
    if uncaptured and not capture_baselines:
        raise GenerateError(
            f"No baseline for {', '.join(uncaptured)}, so those checks can't tell "
            "legacy findings from new ones. To record today's findings as the "
            f'baselines, rerun "alpha bootstrap {target} --capture-baselines".'
        )
    repo_checks = (target / MISE).is_file()
    if repo_checks:
        _require_mise(target)  # before the components' slow steps
    book = project_book(target)
    for c in principles["components"]:
        if only and c["name"] not in only:
            continue
        cwd = target / c["path"]
        if not cwd.is_dir():
            raise GenerateError(
                f'Component "{c["name"]}" folder {cwd} is missing. Fix its path in '
                f"{PRINCIPLES_TOML}, or regenerate the skeleton in an empty folder."
            )
        steps = [
            *(("bootstrap", command) for command in book.get(c["stack"]).bootstrap),
            *check_commands(c["commands"]),
        ]
        own = [m for m in uncaptured if m.partition(":")[2] == c["name"]]
        captured: set[str] = set()
        for step, command in steps:
            if own and step not in ("bootstrap", "setup"):
                _capture(target, own)  # the toolchain is installed by now
                captured |= {m.partition(":")[0] for m in own}
                own = []
            if step in captured:
                continue  # just captured from this very run: it holds
            _run(c["name"], command, cwd, fix)
        _capture(target, own)
    if repo_checks:
        _repo_checks(target, [m for m in uncaptured if ":" not in m])
    refresh_manifest(target)
