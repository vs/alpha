"""bin/alpha-evals run [scenario ...] | check <project> <scenario>."""

import argparse
import shlex
import sys
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from alpha_evals.interview import Config
from alpha_evals.run import (
    PLUGIN_ROOT,
    eval_env,
    prepare_kit,
    project_checks,
    run_scenario,
    summary,
)
from alpha_evals.scenario import SCENARIOS, ScenarioError, load_brief


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="alpha_evals", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run the interview evals headlessly")
    r.add_argument(
        "scenarios", nargs="*", help=f"default: all ({', '.join(SCENARIOS)})"
    )
    r.add_argument("--out", type=Path, help="run folder (default: a new temp folder)")
    r.add_argument("--no-reviewer", action="store_true", help="skip the reviewer probe")
    r.add_argument("--max-usd", type=float, default=Config.max_usd, help="per scenario")
    r.add_argument("--max-exchanges", type=int, default=Config.max_exchanges)
    r.add_argument("--interviewer-model", default=Config.interviewer_model)
    r.add_argument("--user-model", default=Config.user_model)
    r.add_argument("--claude", default="claude", help="the claude command")
    c = sub.add_parser("check", help="run the skeleton checks on a generated project")
    c.add_argument("project", type=Path)
    c.add_argument("scenario", choices=SCENARIOS)
    return p


def _run(args: argparse.Namespace) -> int:
    names: list[str] = args.scenarios or list(SCENARIOS)
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        print(
            f"Unknown scenario {', '.join(unknown)}. "
            f"Choose from: {', '.join(SCENARIOS)}.",
            file=sys.stderr,
        )
        return 2
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir: Path = args.out or Path(tempfile.gettempdir()) / "alpha-evals" / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    kit = run_dir / "kit"
    commit, dirty = prepare_kit(PLUGIN_ROOT, kit)
    if dirty:
        print(
            f"alpha_evals: the kit has uncommitted changes; running HEAD {commit[:7]}"
        )
    env = eval_env(run_dir, kit)
    config = Config(
        claude=tuple(shlex.split(args.claude)),
        interviewer_model=args.interviewer_model,
        user_model=args.user_model,
        max_exchanges=args.max_exchanges,
        max_usd=args.max_usd,
    )
    reports: list[dict[str, Any]] = []
    for name in names:
        report = run_scenario(
            name, run_dir, kit, env, config, not args.no_reviewer, commit, dirty
        )
        cells = " ".join(f"{c['name']}={c['status']}" for c in report["checks"])
        print(f"{name}: {cells} (${report['cost_usd']:.2f})", flush=True)
        reports.append(report)
    path = run_dir / "summary.md"
    path.write_text(summary(reports, commit, dirty), encoding="utf-8")
    print(path)
    failed = any(c["status"] == "fail" for r in reports for c in r["checks"])
    return 1 if failed else 0


def _check(args: argparse.Namespace) -> int:
    project: Path = args.project.resolve()
    with tempfile.TemporaryDirectory() as scratch:
        checks = project_checks(project, load_brief(args.scenario), Path(scratch))
    for c in checks:
        print(f"{c.name}: {c.status}")
        for line in c.detail.splitlines():
            print(f"  {line}")
    return 1 if any(c.status == "fail" for c in checks) else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args) if args.command == "run" else _check(args)
    except ScenarioError as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
