"""`alpha recipe`: list kit recipes, and check, try and save a drafted one."""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from alpha import toml_write
from alpha.answers import PROJECT_JSON, AnswersError, drafted_recipes, write_answers
from alpha.defaults import DefaultsError, Source, SourceNotLive
from alpha.recipes import (
    Recipe,
    RecipeBook,
    check_commands,
    matches,
    recipe_hash,
    render_template,
)

_TAIL_LINES = 40
_NOT_FOUND = 127
_TIMEOUT = 600.0  # seconds per command: a toolchain download can be slow
_SUBJECT = 50  # the commit convention's limit on the description
# How sh, bash and zsh name a command they can't find.
_MISSING = re.compile(
    r"(?:^|: )([^\s:]+): (?:command )?not found$|command not found: (\S+)$", re.M
)


def list_recipes() -> list[str]:
    """The kit's stacks; a broken recipe is listed with its problem."""
    book = RecipeBook()
    lines: list[str] = []
    for stack in book.kit_stacks():
        try:
            proven = book.get(stack).proven
        except AnswersError as e:
            lines.append(f"{stack} (broken: {e})")
            continue
        lines.append(f"{stack} ({'proven' if proven else 'drafted in a project'})")
    return lines


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


def _run(command: str, cwd: Path) -> tuple[int, str] | None:
    """(exit code, output), or None when it ran past the timeout. Nothing
    can answer a prompt, so stdin is empty."""
    print(f"alpha: try: {command}", file=sys.stderr, flush=True)
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,  # so a timeout stops what it started, too
    )
    try:
        output, _ = proc.communicate(timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return None
    return proc.returncode, output


def _missing_tool(command: str, output: str) -> str:
    """The tool the shell couldn't find: named in its output, else the first
    word that isn't an assignment."""
    found = _MISSING.search(output)
    if found:
        return found.group(1) or found.group(2)
    words = [w for w in command.split() if "=" not in w]
    return words[0] if words else command


def _created_sources(root: Path, recipe: Recipe) -> list[str]:
    """Code files in the scratch folder that no template wrote."""
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if (
            path.is_file()
            and rel not in recipe.templates
            and matches(rel, recipe.source_globs)
            and not matches(rel, recipe.test_globs)
            and not matches(rel, recipe.exclude_globs)
        ):
            found.append(rel)
    return found


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
            ran = _run(command, root)
            if ran is None:
                return (
                    f'"{command}" took longer than {_TIMEOUT:g}s, so alpha stopped '
                    f"it. If it waits for input, make the recipe's {step} command "
                    "run without asking; otherwise find out why it's slow, fix it, "
                    f'and run "alpha recipe try {target} {stack}" again.'
                )
            code, output = ran
            if code == 0:
                continue
            tail = "\n".join(output.splitlines()[-_TAIL_LINES:])
            tool = _missing_tool(command, output)
            fix = (
                f"{tool} wasn't found: install {tool} (with your system's package "
                f"manager or the tool's own installer), or fix the recipe's {step} "
                "command"
                if code == _NOT_FOUND
                else f"Fix the recipe's {step} command"
            )
            return (
                f'"{command}" failed (exit {code}). Last lines of its output:\n'
                f"{tail}\n{fix}, save it, and run "
                f'"alpha recipe try {target} {stack}" again.'
            )
        created = _created_sources(root, recipe)
        if created:
            return (
                f"The recipe's commands created source files ({', '.join(created)}). "
                "The skeleton holds no app code: remove the step that creates them "
                f'(e.g. an init command), save it, and run "alpha recipe try {target} '
                f'{stack}" again.'
            )
    drafted = _drafted(target)
    drafted[stack] = {**data, "proven_hash": recipe_hash(data)}
    write_answers(target, json.dumps({"recipes": drafted}))
    return None


def _template_name(rel: str) -> str:
    """Where a template is kept in recipes/<stack>/: its own path, so two
    templates never share a file."""
    return rel + ".tmpl"


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
    if (folder / stack).exists():
        raise AnswersError(
            f"recipes/{stack}/ already exists in the kit source ({folder}). Move it "
            "away or remove it, then retry."
        )
    try:  # render before writing anything, so a failure leaves no files
        text = (
            "# Drafted in a project interview and proven there; less proven than "
            "the kit's own.\n" + toml_write.dumps(toml)
        )
    except TypeError as e:
        raise AnswersError(
            f"recipes.{stack}: can't be written as TOML ({e}). Fix that value in "
            "the drafted recipe, try it again, then save it."
        ) from None
    created_folder = not folder.exists()
    paths = [f"recipes/{stack}.toml", f"recipes/{stack}"]
    try:
        (folder / stack).mkdir(parents=True)
        for rel, template in templates.items():
            path = folder / stack / _template_name(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(template)
        (folder / f"{stack}.toml").write_text(text)
        _git(source.path, "add", "--", *paths)
        subject = f"Add {stack} recipe from {slug}"
        if len(subject) > _SUBJECT:
            subject = f"Add {stack} recipe"
        message = f"feat(recipes): {subject}"
        if trailers:
            message += "\n\n" + "\n".join(trailers)
        _git(source.path, "commit", "-q", "-m", message, "--", *paths)
    except Exception:
        subprocess.run(  # unstage only what this save staged
            ["git", "-C", str(source.path), "reset", "-q", "--", *paths],
            capture_output=True,
        )
        shutil.rmtree(folder / stack, ignore_errors=True)
        (folder / f"{stack}.toml").unlink(missing_ok=True)
        if created_folder:
            shutil.rmtree(folder, ignore_errors=True)
        raise
    return _git(source.path, "rev-parse", "--short", "HEAD")
