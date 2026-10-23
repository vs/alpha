"""`alpha recipe`: list kit recipes, and check, try and save a drafted one."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from alpha.answers import PROJECT_JSON, AnswersError, drafted_recipes, write_answers
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
