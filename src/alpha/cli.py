import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from alpha import VERSION, answers, defaults, toml_write
from alpha.generate import (
    PRINCIPLES_TOML,
    PROJECT_JSON,
    GenerateError,
    bootstrap,
    generate,
    load_project_principles,
)
from alpha.gitops import commit_skeleton

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
    gen = sub.add_parser("generate", help="write the skeleton into an empty folder")
    gen.add_argument("target", type=Path, help="folder holding the interview answers")
    boot = sub.add_parser("bootstrap", help="install toolchains and run the tests")
    boot.add_argument("target", type=Path, help="a generated project")
    cs = sub.add_parser("commit-skeleton", help="commit the skeleton in groups")
    cs.add_argument("target", type=Path, help="a generated project")
    cs.add_argument("--trailer", action="append", default=[], help="commit trailer")
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


def _answers(args: argparse.Namespace) -> int:
    try:
        answers.load_answers(args.path, args.area or answers.AREAS)
    except answers.AnswersError as e:
        print(e, file=sys.stderr)
        return 1
    print("ok")
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


def _project(args: argparse.Namespace) -> int:
    target: Path = args.target
    generating = args.command == "generate"
    rerun = f'"alpha {args.command} {target}"'
    try:
        if generating:
            _generate(target)
        elif args.command == "bootstrap":
            _bootstrap(target)
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
    if args.command in ("generate", "bootstrap", "commit-skeleton"):
        return _project(args)
    return 2  # unreachable: argparse rejects unknown commands


if __name__ == "__main__":
    sys.exit(main())
