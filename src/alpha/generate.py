"""Generate a project skeleton from the interview answers, then bootstrap it."""

import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path
from typing import Any, cast

from alpha import VERSION
from alpha.answers import PROJECT_JSON, drafted_recipes, load_answers
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles, render_principles
from alpha.recipes import RecipeBook, check_commands, render_component
from alpha.render.ci import render_ci, render_dependabot
from alpha.render.claude_settings import render_settings
from alpha.render.docs import render_docs

PRINCIPLES_TOML = "docs/principles.toml"
_ALLOWED_FILES = frozenset({PROJECT_JSON, ".claude/settings.local.json"})
_ALLOWED_DIRS = frozenset({".claude", ".claude/alpha"})
_TAIL_LINES = 40


class GenerateError(Exception):
    pass


def _unexpected(target: Path) -> list[str]:
    """Entries that make the target non-empty, relative to it."""
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


def _gitignore(principles: dict[str, Any], book: RecipeBook) -> str:
    # Hooks run with python3, which leaves bytecode next to them.
    lines = [
        ".claude/alpha/state/",
        ".claude/settings.local.json",
        ".DS_Store",
        ".claude/alpha/hooks/__pycache__/",
        # Secrets live in .env files at any depth; the example documents them.
        ".env",
        ".env.*",
        "**/.env",
        "**/.env.*",
        "!.env.example",
    ]
    for c in principles["components"]:
        for entry in book.get(c["stack"]).ignores:
            # "**/" keeps the any-depth match the unprefixed pattern has.
            lines.append(entry if c["path"] == "." else f"{c['path']}/**/{entry}")
    return "\n".join(lines) + "\n"


def _copies(plugin_root: Path) -> dict[str, Path]:
    files = plugin_root / "project-files"
    out = {
        f".claude/alpha/hooks/{p.name}": p
        for p in sorted((files / "hooks").glob("*.py"))
    }
    out[".claude/skills/commit/SKILL.md"] = files / "skills/commit/SKILL.md"
    out[".claude/skills/decision/SKILL.md"] = files / "skills/decision/SKILL.md"
    out[".claude/agents/committer.md"] = files / "agents/committer.md"
    out[".claude/agents/principles-reviewer.md"] = (
        files / "agents/principles-reviewer.md"
    )
    out[".claude/alpha/githooks/commit-msg"] = files / "githooks/commit-msg"
    return out


def _display_path(path: Path) -> str:
    """The path with the home directory shown as ~, so no username is committed."""
    try:
        return f"~/{path.relative_to(Path.home()).as_posix()}"
    except ValueError:
        return str(path)


def _source_commit(source: Source) -> str | None:
    if not source.live:
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


def generate(
    target: Path,
    plugin_root: Path,
    source: Source,
    year: int,
    today: date | None = None,
) -> list[str]:
    """Write the skeleton into an empty target; return the sorted relpaths."""
    if not target.is_dir():
        raise GenerateError(
            f"{target} is not a folder. Create it and run the alpha interview "
            "there first."
        )
    extra = _unexpected(target)
    if extra:
        raise GenerateError(
            f"{target} is not empty (found: {', '.join(extra)}). alpha v0.1 starts "
            "projects only in empty folders. Choose a new folder, or move these "
            "files out first."
        )
    answers_path = target / PROJECT_JSON
    a = load_answers(answers_path)
    principles = build_principles(load_defaults(source), a, VERSION)
    book = a.book()

    # Render everything before writing anything, so a failure leaves no debris.
    texts: dict[str, str] = {PRINCIPLES_TOML: render_principles(principles)}
    today = today or date.today()
    texts.update(render_docs(a, principles, year, today, root=target))
    component_files: dict[str, tuple[str, str]] = {}  # path -> (text, stack)
    for c in a.components:
        rendered = render_component(c, principles["project"]["slug"], book.get(c.stack))
        component_files.update({rel: (text, c.stack) for rel, text in rendered.items()})
    texts[".claude/settings.json"] = (
        json.dumps(render_settings(principles, book), indent=2) + "\n"
    )
    texts[".gitignore"] = _gitignore(principles, book)
    assert a.build is not None  # build_principles refuses answers without it
    texts.update(render_ci(principles, a.build.ci, book))
    assert a.dependencies is not None
    texts.update(
        render_dependabot(
            principles,
            a.dependencies.updates,
            a.dependencies.schedule,
            a.build.ci,
            book,
        )
    )
    copies = _copies(plugin_root)
    for rel, (text, stack) in component_files.items():
        if rel in texts or rel in copies:
            raise GenerateError(
                f"The {stack} recipe's template {rel} collides with a file alpha "
                "generates. Remove that template from the recipe (alpha writes the "
                "file itself), then retry."
            )
        texts[rel] = text

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
        "defaults": {
            "path": _display_path(source.path),
            "live": source.live,
            "commit": _source_commit(source),
        },
        "files": _hashes(target, generated),
    }
    _write_json(answers_path, data)
    return sorted([*generated, PROJECT_JSON])


def _hashes(target: Path, rels: list[str]) -> dict[str, str]:
    return {
        rel: hashlib.sha256((target / rel).read_bytes()).hexdigest() for rel in rels
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


def refresh_manifest(target: Path) -> None:
    """Rehash the generated files, which bootstrap's package managers change."""
    path = target / PROJECT_JSON
    try:
        data = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        files = cast(dict[str, str], data["manifest"]["files"])
    except (OSError, ValueError, KeyError, TypeError):
        return  # no manifest to keep in step (e.g. a hand-made project)
    present = [rel for rel in files if (target / rel).is_file()]
    data["manifest"]["files"] = _hashes(target, present)
    _write_json(path, data)


def load_project_principles(target: Path) -> dict[str, Any]:
    path = target / PRINCIPLES_TOML
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise GenerateError(
            f'{path} not found. Run "alpha generate {target}" first, in a folder '
            "that holds the interview answers."
        ) from None
    except tomllib.TOMLDecodeError as e:
        raise GenerateError(
            f"{path} is not valid TOML ({e}). Fix the syntax, then retry."
        ) from None


def project_book(target: Path) -> RecipeBook:
    """The kit's recipes plus any the project's interview drafted."""
    try:
        data = json.loads((target / PROJECT_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return RecipeBook()
    if not isinstance(data, dict):
        return RecipeBook()
    raw: object = cast(dict[str, Any], data).get("recipes", {})
    return RecipeBook(drafted_recipes(raw))


def bootstrap(target: Path, principles: dict[str, Any]) -> None:
    """Per component: install the toolchain, then run every check CI runs.

    Then rehash the manifest, so it matches the files commit-skeleton commits.
    """
    fix = (
        "Fix the failing step (is the component's toolchain installed?) and rerun "
        f'"alpha bootstrap {target}"'
    )
    book = project_book(target)
    for c in principles["components"]:
        cwd = target / c["path"]
        if not cwd.is_dir():
            raise GenerateError(
                f'Component "{c["name"]}" folder {cwd} is missing. Fix its path in '
                f"{PRINCIPLES_TOML}, or regenerate the skeleton in an empty folder."
            )
        missing = [s for s in ("setup", "test") if s not in c["commands"]]
        if missing:
            raise KeyError(missing[0])  # explained as a damaged principles file
        commands = [
            *book.get(c["stack"]).bootstrap,
            *(command for _, command in check_commands(c["commands"])),
        ]
        for command in commands:
            print(f"alpha: {c['name']}: {command}", file=sys.stderr, flush=True)
            done = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if done.returncode != 0:
                tail = "\n".join(done.stdout.splitlines()[-_TAIL_LINES:])
                raise GenerateError(
                    f'"{command}" failed in {cwd} (exit {done.returncode}). '
                    f"Last lines of its output:\n{tail}\n{fix}"
                )
    refresh_manifest(target)
