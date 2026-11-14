import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from alpha import toml_write
from alpha.answers import PROJECT_JSON, AnswersError, drafted_recipes, write_answers
from alpha.baseline import Baseline, findings
from alpha.defaults import USER_RECIPES, DefaultsError, Source
from alpha.recipes import (
    Recipe,
    RecipeBook,
    check_commands,
    matches,
    recipe_hash,
    render_template,
)
from alpha.shell import Ran, run_command

_TAIL_LINES = 40
_NOT_FOUND = 127
_TIMEOUT_SECONDS = 600.0
# How sh, bash and zsh name a command they can't find.
_MISSING = re.compile(
    r"(?:^|: )([^\s:]+): (?:command )?not found$|command not found: (\S+)$", re.M
)


def list_recipes() -> list[str]:
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
    drafted = _drafted(target)
    if stack not in drafted:
        raise AnswersError(
            f'recipes: no drafted recipe for "{stack}" in {target / PROJECT_JSON}. '
            "Draft it with the stack-recipe skill and save it with answers write."
        )
    drafted_recipes({stack: drafted[stack]})
    return cast(dict[str, Any], drafted[stack])


def _run(command: str, cwd: Path, merge: bool = True) -> Ran | None:
    print(f"alpha: try: {command}", file=sys.stderr, flush=True)
    return run_command(command, cwd, _TIMEOUT_SECONDS, merge=merge)


def _missing_tool(command: str, output: str) -> str:
    found = _MISSING.search(output)
    if found:
        return found.group(1) or found.group(2)
    words = [w for w in command.split() if "=" not in w]
    return words[0] if words else command


def _created_sources(root: Path, recipe: Recipe) -> list[str]:
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


def _baseline_problem(
    step: str, baseline: Baseline, root: Path, target: Path, stack: str
) -> str | None:
    """On the clean skeleton, a baseline's command must read as no findings:
    a failure it can't read, or a finding, means the reader is wrong."""
    print(f"alpha: try: {baseline.command}", file=sys.stderr, flush=True)
    again = f'save it, and run "alpha recipe try {target} {stack}" again.'
    try:
        done = subprocess.run(
            baseline.command,
            shell=True,
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return (
            f'"{baseline.command}" took longer than {_TIMEOUT_SECONDS:g}s. Fix the '
            f"recipe's baseline.{step} command, {again}"
        )
    tail = "\n".join((done.stdout + done.stderr).splitlines()[-_TAIL_LINES:])
    try:
        found = findings(baseline, done.stdout, done.stderr, root, root)
    except ValueError as e:
        return (
            f'"{baseline.command}" printed output its baseline.{step} reader can\'t '
            f"read ({e}). Last lines:\n{tail}\nFix the recipe's baseline.{step}, "
            + again
        )
    if found:
        lines = "\n".join(f"  {text}" for _, _, text in found[:10])
        return (
            f"baseline.{step} reads findings on the clean skeleton:\n{lines}\n"
            "The checks pass there, so its pattern matches lines that aren't "
            f"findings (such as a summary). Narrow it, {again}"
        )
    if done.returncode != 0:
        return (
            f'"{baseline.command}" failed (exit {done.returncode}) on the clean '
            f"skeleton, though the {step} check passed. Last lines:\n{tail}\n"
            f"Fix the recipe's baseline.{step} command, {again}"
        )
    return None


def _users(target: Path, stack: str) -> list[str]:
    """The folders of the components project.json gives the stack."""
    try:
        data: object = json.loads((target / PROJECT_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    comps: object = (
        cast(dict[str, Any], data).get("components") if isinstance(data, dict) else None
    )
    paths: list[str] = []
    for entry in cast(list[object], comps) if isinstance(comps, list) else []:
        if not isinstance(entry, dict):
            continue
        c = cast(dict[str, object], entry)
        if c.get("stack") == stack and isinstance(c.get("path"), str):
            paths.append(str(c["path"]))
    return paths


def _git_out(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(target), *args], capture_output=True, text=True
    )


def _timed_out(command: str, step: str, again: str) -> str:
    return (
        f'"{command}" took longer than {_TIMEOUT_SECONDS:g}s, so alpha stopped it. '
        f"If it waits for input, make the recipe's {step} command run without "
        f"asking; otherwise find out why it's slow, fix it, and {again}"
    )


def _prove_step(
    recipe: Recipe, step: str, command: str, cwd: Path, tree: Path, again: str
) -> tuple[str | None, str | None]:
    """(problem, report) for one check of an adopted recipe on the repo."""
    ran = _run(command, cwd, merge=False)
    if ran is None:
        return _timed_out(command, step, again), None
    code, out, err = ran.code, ran.out, ran.err
    if code == 0:
        return None, None
    tail = "\n".join((out + err).splitlines()[-_TAIL_LINES:])
    if code == _NOT_FOUND:
        tool = _missing_tool(command, out + err)
        return (
            f'{tool} wasn\'t found running "{command}". Install it, or fix the '
            f"recipe's {step} command, then {again}",
            None,
        )
    if step == "format_check":
        return (
            f"\"{command}\" fails: today's code isn't formatted. Set "
            'commands.format_check to "" for now: the adoption plan formats each '
            f"component in a commit of its own and turns it back on. Then {again}",
            None,
        )
    reader = recipe.baselines.get(step)
    if reader is None:
        return (
            f'"{command}" fails on today\'s code (exit {code}). Last lines:\n'
            f"{tail}\nAdd [baseline.{step}] (a command with machine-readable "
            "output and a pattern for each finding's file and rule) so its legacy "
            f"findings can be baselined, or fix them first; then {again}",
            None,
        )
    read = _run(reader.command, cwd, merge=False)
    if read is None:
        return _timed_out(reader.command, f"baseline.{step}", again), None
    rout, rerr = read.out, read.err
    rtail = "\n".join((rout + rerr).splitlines()[-_TAIL_LINES:])
    try:
        found = findings(reader, rout, rerr, tree, cwd)
    except ValueError as e:
        return (
            f'"{reader.command}" printed output its baseline.{step} reader can\'t '
            f"read ({e}). Last lines:\n{rtail}\nFix the recipe's "
            f"baseline.{step}, then {again}",
            None,
        )
    if not found:
        return (
            f'"{command}" fails, but baseline.{step} ("{reader.command}") reads no '
            f"findings in its output, so they couldn't be baselined. Last lines:\n"
            f"{rtail}\nFix the reader's pattern against this output, then {again}",
            None,
        )
    files = len({f for f, _, _ in found})
    return None, f"{step}: {len(found)} findings in {files} files"


def _try_adopted(
    target: Path, stack: str, recipe: Recipe, report: list[str]
) -> str | None:
    """Prove an adopted recipe on a worktree of the repo's HEAD (spec §5b)."""
    again = f'run "alpha recipe try {target} {stack}" again.'
    paths = _users(target, stack)
    if not paths:
        return (
            f"No component uses the {stack} recipe yet, so alpha doesn't know where "
            "to prove it. Save the components (with this stack) first, then " + again
        )
    head = _git_out(target, "rev-parse", "--short", "HEAD")
    if head.returncode != 0:
        return (
            f"{target} has no commit to prove the recipe on "
            f"({head.stderr.strip()}). Commit the code, then " + again
        )
    with tempfile.TemporaryDirectory(prefix="alpha-try-") as scratch:
        tree = Path(scratch) / "repo"
        added = _git_out(
            target, "worktree", "add", "--detach", "--quiet", str(tree), "HEAD"
        )
        if added.returncode != 0:
            return (
                f"git couldn't make a worktree of {target} to prove the recipe on "
                f"({added.stderr.strip()}). Fix that, then " + again
            )
        try:
            for path in paths:
                cwd = tree if path == "." else tree / path
                for step, command in check_commands(recipe.commands):
                    if step == "setup":
                        ran = _run(command, cwd)
                        if ran is None:
                            return _timed_out(command, step, again)
                        if ran.code != 0:
                            tail = "\n".join(ran.out.splitlines()[-_TAIL_LINES:])
                            return (
                                f'"{command}" failed in {path} (exit {ran.code}). Last '
                                f"lines:\n{tail}\nFix the recipe's setup command, "
                                "then " + again
                            )
                        continue
                    problem, line = _prove_step(recipe, step, command, cwd, tree, again)
                    if problem:
                        return f"{path}: {problem}"
                    if line:
                        report.append(f"{path}: {line}")
        finally:
            _git_out(target, "worktree", "remove", "--force", str(tree))
            _git_out(target, "worktree", "prune")
    report.insert(0, f"on {', '.join(paths)} at {head.stdout.strip()}")
    return None


def try_recipe(target: Path, stack: str, report: list[str] | None = None) -> str | None:
    """Prove a drafted recipe; `report` collects what an adopted one found."""
    data = check(target, stack)
    recipe = drafted_recipes({stack: data})[stack]
    if recipe.adopted:
        problem = _try_adopted(target, stack, recipe, [] if report is None else report)
        if problem is None:
            _save_proof(target, stack, data)
        return problem
    with tempfile.TemporaryDirectory(prefix="alpha-try-") as scratch:
        root = Path(scratch)
        for rel, text in recipe.templates.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_template(text, {"name": stack, "slug": "try"}))
        steps = [("bootstrap", c) for c in recipe.bootstrap]
        steps += check_commands(recipe.commands)
        for step, command in steps:
            ran = _run(command, root)
            if ran is None:
                return (
                    f'"{command}" took longer than {_TIMEOUT_SECONDS:g}s, so alpha '
                    f"stopped it. If it waits for input, make the recipe's {step} "
                    "command run without asking; otherwise find out why it's slow, "
                    f'fix it, and run "alpha recipe try {target} {stack}" again.'
                )
            code, output = ran.code, ran.out
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
        for step, baseline in recipe.baselines.items():
            problem = _baseline_problem(step, baseline, root, target, stack)
            if problem:
                return problem
        created = _created_sources(root, recipe)
        if created:
            return (
                f"The recipe's commands created source files ({', '.join(created)}). "
                "The skeleton holds no app code: remove the step that creates them "
                f'(e.g. an init command), save it, and run "alpha recipe try {target} '
                f'{stack}" again.'
            )
    _save_proof(target, stack, data)
    return None


def _save_proof(target: Path, stack: str, data: dict[str, Any]) -> None:
    drafted = _drafted(target)
    drafted[stack] = {**data, "proven_hash": recipe_hash(data)}
    write_answers(target, json.dumps({"recipes": drafted}))


def _template_name(rel: str) -> str:
    return rel + ".tmpl"


def save_recipe(target: Path, stack: str, source: Source) -> Path:
    if source.user is None:
        raise DefaultsError(
            "Cannot save a recipe: there is no folder for your alpha recipes. Set "
            "ALPHA_CONFIG_DIR to one, then retry."
        )
    data = check(target, stack)
    if data.get("proven_hash") != recipe_hash(data):
        raise AnswersError(
            f'recipes.{stack}: not proven since it last changed. Run "alpha recipe '
            f'try {target} {stack}" until it prints ok, then save it.'
        )
    folder = source.user / USER_RECIPES
    saved = folder / f"{stack}.toml"
    if saved.exists() or (folder / stack).exists():
        raise AnswersError(
            f"recipes.{stack}: you already saved a {stack} recipe in {folder}. Keep "
            f"using it, or remove {saved} and {folder / stack} to save this one."
        )
    if stack in RecipeBook().kit_stacks():
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
    try:
        text = (
            f"# Drafted in the {slug} interview and proven there; less proven than "
            "the kit's own.\n" + toml_write.dumps(toml)
        )
    except TypeError as e:
        raise AnswersError(
            f"recipes.{stack}: can't be written as TOML ({e}). Fix that value in "
            "the drafted recipe, try it again, then save it."
        ) from None
    try:
        (folder / stack).mkdir(parents=True)
        for rel, template in templates.items():
            path = folder / stack / _template_name(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(template)
        saved.write_text(text)
    except OSError:
        shutil.rmtree(folder / stack, ignore_errors=True)
        saved.unlink(missing_ok=True)
        raise
    return saved
