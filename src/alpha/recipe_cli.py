"""`alpha recipe`: list kit recipes, and check, try and save a drafted one."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from alpha import toml_write
from alpha.answers import PROJECT_JSON, AnswersError, drafted_recipes, write_answers
from alpha.defaults import DefaultsError, Source, SourceNotLive
from alpha.recipes import (
    RecipeBook,
    check_commands,
    recipe_hash,
    render_template,
)

_TAIL_LINES = 40
_NOT_FOUND = 127


def list_recipes() -> list[str]:
    book = RecipeBook()
    return [
        f"{stack} ({'proven' if book.get(stack).proven else 'drafted in a project'})"
        for stack in book.kit_stacks()
    ]


def _drafted(target: Path) -> dict[str, Any]:
    path = target / PROJECT_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise AnswersError(
            f"{path}: can't read the interview answers ({e}). Run the interview "
            "there first, or pass the project folder."
        ) from None
    if not isinstance(data, dict):
        return {}
    raw: object = cast(dict[str, Any], data).get("recipes", {})
    return cast(dict[str, Any], raw) if isinstance(raw, dict) else {}


def check(target: Path, stack: str) -> dict[str, Any]:
    """The drafted recipe's data, validated; AnswersError when it isn't usable."""
    drafted = _drafted(target)
    if stack not in drafted:
        raise AnswersError(
            f'recipes: no drafted recipe for "{stack}" in {target / PROJECT_JSON}. '
            "Draft it with the stack-recipe skill and save it with answers write."
        )
    drafted_recipes({stack: drafted[stack]})
    return cast(dict[str, Any], drafted[stack])


def _run(command: str, cwd: Path) -> tuple[int, str]:
    print(f"alpha: try: {command}", file=sys.stderr, flush=True)
    done = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return done.returncode, done.stdout


def try_recipe(target: Path, stack: str) -> str | None:
    """Prove the drafted recipe in a scratch folder: write its templates, then
    run its bootstrap and every check step. None on success (the proof is
    recorded), else what failed and how to fix it."""
    data = check(target, stack)
    recipe = drafted_recipes({stack: data})[stack]
    with tempfile.TemporaryDirectory(prefix="alpha-try-") as scratch:
        root = Path(scratch)
        for rel, text in recipe.templates.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_template(text, stack, "try"))
        steps = [("bootstrap", c) for c in recipe.bootstrap]
        steps += check_commands(recipe.commands)
        for step, command in steps:
            code, output = _run(command, root)
            if code == 0:
                continue
            tail = "\n".join(output.splitlines()[-_TAIL_LINES:])
            tool = command.split()[0] if command.split() else command
            fix = (
                f"{tool} wasn't found: install {tool}, or fix the recipe's {step} "
                "command"
                if code == _NOT_FOUND
                else f"Fix the recipe's {step} command"
            )
            return (
                f'"{command}" failed (exit {code}). Last lines of its output:\n'
                f"{tail}\n{fix}, save it, and run "
                f'"alpha recipe try {target} {stack}" again.'
            )
    drafted = _drafted(target)
    drafted[stack] = {**data, "proven_hash": recipe_hash(data)}
    write_answers(target, json.dumps({"recipes": drafted}))
    return None


def _template_name(rel: str) -> str:
    return rel.replace("/", "-") + ".tmpl"


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    if done.returncode != 0:
        raise DefaultsError(
            f"git {args[0]} failed in {repo}: {done.stderr.strip()}. Fix the "
            "repository state there, then retry."
        )
    return done.stdout.strip()


def save_recipe(target: Path, stack: str, source: Source, trailers: list[str]) -> str:
    """Copy a proven drafted recipe into the kit source as recipes/<stack>.toml
    plus its templates, and commit them. Returns the short commit hash."""
    if not source.live:
        raise SourceNotLive(
            "Cannot save a recipe to the kit: no alpha source checkout is "
            f"available ({source.reason}). Set ALPHA_SOURCE to your alpha "
            "checkout and retry, or keep the recipe in this project only."
        )
    data = check(target, stack)
    if data.get("proven_hash") != recipe_hash(data):
        raise AnswersError(
            f'recipes.{stack}: not proven since it last changed. Run "alpha recipe '
            f'try {target} {stack}" until it prints ok, then save it.'
        )
    if (
        stack in RecipeBook().kit_stacks()
        or (source.path / "recipes" / f"{stack}.toml").exists()
    ):
        raise AnswersError(
            f"recipes.{stack}: the kit already has a {stack} recipe. Keep using it, "
            "or change the kit's recipe by hand."
        )
    answers = json.loads((target / PROJECT_JSON).read_text(encoding="utf-8"))
    slug = str(answers.get("identity", {}).get("slug") or target.name)
    templates: dict[str, str] = dict(data["templates"])
    fields = {
        k: v for k, v in data.items() if k not in ("templates", "proven_hash", "proven")
    }
    toml = {"stack": stack, "proven": False, **fields}
    toml["files"] = {rel: _template_name(rel) for rel in templates}
    folder = source.path / "recipes"
    written = [folder / f"{stack}.toml", folder / stack]
    created_folder = not folder.exists()
    try:
        (folder / stack).mkdir(parents=True)
        for rel, text in templates.items():
            (folder / stack / _template_name(rel)).write_text(text)
        (folder / f"{stack}.toml").write_text(
            "# Drafted in a project interview and proven there; less proven than "
            "the kit's own.\n" + toml_write.dumps(toml)
        )
        paths = [str(p.relative_to(source.path)) for p in written]
        _git(source.path, "add", "--", *paths)
        message = f"feat(recipes): Add {stack} recipe from {slug}"
        if trailers:
            message += "\n\n" + "\n".join(trailers)
        _git(source.path, "commit", "-q", "-m", message, "--", *paths)
    except (DefaultsError, OSError):
        subprocess.run(
            ["git", "-C", str(source.path), "reset", "-q", "--", "recipes"],
            capture_output=True,
        )
        shutil.rmtree(folder / stack, ignore_errors=True)
        (folder / f"{stack}.toml").unlink(missing_ok=True)
        if created_folder:
            shutil.rmtree(folder, ignore_errors=True)
        raise
    return _git(source.path, "rev-parse", "--short", "HEAD")
