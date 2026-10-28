import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from alpha import VERSION, answers, defaults, recipe_cli, toml_write
from alpha.generate import (
    PRINCIPLES_TOML,
    PROJECT_JSON,
    GenerateError,
    bootstrap,
    generate,
    load_project_principles,
)
from alpha.gitops import commit_skeleton
from alpha.update import PROPOSALS, apply_update, describe, plan_diff, plan_update

PLUGIN_ROOT: Path = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alpha")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="print the alpha version")
    d = sub.add_parser("defaults", help="show or change kit defaults")
    dsub = d.add_subparsers(dest="defaults_command", required=True)
    show = dsub.add_parser("show", help="print the merged kit defaults")
    show.add_argument("--json", action="store_true", help="machine-readable output")
    dset = dsub.add_parser("set", help="record a new kit default (after user consent)")
    dset.add_argument("--key", required=True, help="dotted key, e.g. review.max_lines")
    dset.add_argument("--value", required=True, help="TOML value, or a plain string")
    dset.add_argument("--project", required=True, help="project that prompted this")
    dset.add_argument("--reason", required=True, help="why the default changes")
    dset.add_argument("--trailer", action="append", default=[], help="commit trailer")
    a = sub.add_parser("answers", help="work with the interview answers file")
    asub = a.add_subparsers(dest="answers_command", required=True)
    check = asub.add_parser("check", help="validate an answers file")
    check.add_argument("path", type=Path, help="usually .claude/alpha/project.json")
    check.add_argument(
        "--area",
        action="append",
        choices=answers.AREAS,
        help="only require this area to be done (repeatable)",
    )
    awrite = asub.add_parser(
        "write", help="merge a JSON object from stdin into the answers file"
    )
    awrite.add_argument("target", type=Path, help="the folder being set up")
    awrite.add_argument("--json", help="the JSON object to merge (default: stdin)")
    r = sub.add_parser("recipe", help="kit recipes and drafted ones")
    rsub = r.add_subparsers(dest="recipe_command", required=True)
    rsub.add_parser("list", help="the kit's stacks")
    for name, text in (
        ("check", "validate a drafted recipe"),
        ("try", "prove a drafted recipe in a scratch folder"),
    ):
        rp = rsub.add_parser(name, help=text)
        rp.add_argument("target", type=Path, help="the folder being set up")
        rp.add_argument("stack", help="the drafted recipe's stack, e.g. rust")
    rsave = rsub.add_parser("save", help="add a proven drafted recipe to the kit")
    rsave.add_argument("target", type=Path, help="the generated project")
    rsave.add_argument("stack", help="the drafted recipe's stack, e.g. rust")
    rsave.add_argument("--trailer", action="append", default=[], help="commit trailer")
    gen = sub.add_parser("generate", help="write the skeleton into an empty folder")
    gen.add_argument("target", type=Path, help="folder holding the interview answers")
    boot = sub.add_parser("bootstrap", help="install toolchains and run the tests")
    boot.add_argument("target", type=Path, help="a generated project")
    cs = sub.add_parser("commit-skeleton", help="commit the skeleton in groups")
    cs.add_argument("target", type=Path, help="a generated project")
    cs.add_argument("--trailer", action="append", default=[], help="commit trailer")
    up = sub.add_parser("update", help="merge changed answers into the project")
    up.add_argument("target", type=Path, help="a generated project")
    up.add_argument(
        "--dry-run", action="store_true", help="show the changes, write nothing"
    )
    return parser


def _defaults(args: argparse.Namespace) -> int:
    try:
        source = defaults.locate_source(PLUGIN_ROOT, os.environ, Path.home())
        if args.defaults_command == "set":
            print(
                defaults.set_default(
                    source,
                    args.key,
                    args.value,
                    args.project,
                    args.reason,
                    args.trailer,
                    date.today(),
                )
            )
            return 0
        merged = defaults.load_defaults(source)
    except defaults.SourceNotLive as e:
        print(e, file=sys.stderr)
        return 4
    except defaults.DefaultsError as e:
        print(e, file=sys.stderr)
        return 3
    if args.json:
        info = {"path": str(source.path), "live": source.live, "reason": source.reason}
        print(json.dumps({"source": info, "defaults": merged}, indent=2))
    else:
        print(
            f"live from {source.path}" if source.live else f"bundled ({source.reason})"
        )
        print(toml_write.dumps(merged), end="")
    return 0


def _answers_input(given: str | None) -> str:
    if given is not None:
        return given
    how = "Pass the answers as one argument: answers write <target> --json '{...}'"
    if sys.stdin.isatty():
        raise answers.AnswersError(f"input: no answers given. {how}")
    try:
        return sys.stdin.read()
    except UnicodeDecodeError:
        raise answers.AnswersError(
            f"input: the answers aren't valid UTF-8 text. {how}"
        ) from None


def _answers(args: argparse.Namespace) -> int:
    if args.answers_command == "write":
        try:
            answers.write_answers(args.target, _answers_input(args.json))
        except answers.AnswersError as e:
            print(e, file=sys.stderr)
            return 3
        print("ok")
        return 0
    try:
        answers.load_answers(args.path, args.area or answers.AREAS)
    except answers.AnswersError as e:
        print(e, file=sys.stderr)
        return 1
    print("ok")
    return 0


def _recipe(args: argparse.Namespace) -> int:
    try:
        if args.recipe_command == "list":
            print("\n".join(recipe_cli.list_recipes()))
            return 0
        if args.recipe_command == "check":
            recipe_cli.check(args.target, args.stack)
            print("ok")
            return 0
        if args.recipe_command == "save":
            source = defaults.locate_source(PLUGIN_ROOT, os.environ, Path.home())
            short = recipe_cli.save_recipe(
                args.target, args.stack, source, args.trailer
            )
            print(f"saved: {args.stack} recipe, commit {short}")
            return 0
        problem = recipe_cli.try_recipe(args.target, args.stack)
    except defaults.SourceNotLive as e:
        print(e, file=sys.stderr)
        return 4
    except defaults.DefaultsError as e:
        print(e, file=sys.stderr)
        return 3
    except answers.AnswersError as e:
        print(e, file=sys.stderr)
        return 3 if args.recipe_command == "save" else 1
    except OSError as e:
        print(
            f"Could not write {e.filename or 'a file'}: {e.strerror or e}. Check "
            "permissions and free space, then retry.",
            file=sys.stderr,
        )
        return 3
    if problem:
        print(problem, file=sys.stderr)
        return 1
    print(f"ok: {args.stack} recipe proven")
    return 0


def _generate(target: Path) -> None:
    source = defaults.locate_source(PLUGIN_ROOT, os.environ, Path.home())
    if not source.live:
        print(f"warning: using bundled kit defaults ({source.reason})", file=sys.stderr)
    files = generate(target, PLUGIN_ROOT, source, date.today().year)
    print(f"Generated {len(files)} files in {target}.")
    print(f'Next: "alpha bootstrap {target}".')


def _bootstrap(target: Path) -> None:
    principles = load_project_principles(target)
    bootstrap(target, principles)
    names = ", ".join(c["name"] for c in principles["components"])
    print(f"Bootstrapped {names}: toolchains installed, tests green.")


def _commit_skeleton(target: Path, trailers: list[str]) -> None:
    hashes = commit_skeleton(target, load_project_principles(target), trailers)
    print(f"Committed {len(hashes)} commits in {target}:")
    if hashes:
        log = subprocess.run(
            ["git", "-C", str(target), "show", "-s", "--format=%h %s", *hashes],
            capture_output=True,
            text=True,
        )
        print(log.stdout, end="")


def _update(target: Path, dry_run: bool) -> None:
    source = defaults.locate_source(PLUGIN_ROOT, os.environ, Path.home())
    plan = plan_update(target, source, date.today())
    if dry_run:
        print(describe(plan, target))
        print(plan_diff(plan, target), end="")
        return
    if not plan.changes and not plan.new_components:
        print(describe(plan, target))  # nothing to change: write nothing
        return
    apply_update(target, plan)
    print(describe(plan, target))
    for c in plan.changes:
        if c.kind == "conflict":
            print(f"{c.path}: merge by hand; proposal: {PROPOSALS}/{c.path}")


def _project(args: argparse.Namespace) -> int:
    target: Path = args.target
    generating = args.command == "generate"
    rerun = f'"alpha {args.command} {target}"'
    try:
        if generating:
            _generate(target)
        elif args.command == "bootstrap":
            _bootstrap(target)
        elif args.command == "update":
            _update(target, args.dry_run)
        else:
            _commit_skeleton(target, args.trailer)
    except (GenerateError, answers.AnswersError, defaults.DefaultsError) as e:
        print(e, file=sys.stderr)
        return 1
    except ValueError as e:  # e.g. a stack without a recipe
        where = "the interview answers" if generating else PRINCIPLES_TOML
        print(f"{where}: {e}", file=sys.stderr)
        return 1
    except KeyError as e:  # a hand-edited file lost a required entry
        if generating:
            print(
                f"The kit defaults are missing {e}. Check them with "
                '"alpha defaults show", restore defaults/defaults.toml, then retry.',
                file=sys.stderr,
            )
        else:
            print(
                f"{PRINCIPLES_TOML} is missing {e}. Restore it with "
                f'"git checkout {PRINCIPLES_TOML}" or regenerate, then rerun {rerun}.',
                file=sys.stderr,
            )
        return 1
    except OSError as e:
        verb, cleanup = ("access", "")
        if generating:
            verb, cleanup = ("write", ", empty the folder except " + PROJECT_JSON)
        print(
            f"Could not {verb} {e.filename or target}: {e.strerror or e}. Check "
            f"permissions and free space{cleanup}, then rerun {rerun}.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print(VERSION)
        return 0
    if args.command == "defaults":
        return _defaults(args)
    if args.command == "answers":
        return _answers(args)
    if args.command == "recipe":
        return _recipe(args)
    if args.command in ("generate", "bootstrap", "commit-skeleton", "update"):
        return _project(args)
    return 2  # unreachable: argparse rejects unknown commands


if __name__ == "__main__":
    sys.exit(main())
