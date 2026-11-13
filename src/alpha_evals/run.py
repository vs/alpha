import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from alpha.answers import PROJECT_JSON
from alpha.cli import PLUGIN_ROOT
from alpha_evals.checks import (
    Check,
    check_answers,
    check_commits,
    check_files,
    check_repo_checks,
    check_settings,
)
from alpha_evals.interview import Config, interview
from alpha_evals.reviewer import check_reviewer
from alpha_evals.scenario import Brief, load_brief
from alpha_evals.seeded import check_commands, check_hooks, check_repo_seeds

__all__ = ["PLUGIN_ROOT", "eval_env", "prepare_kit", "run_scenario", "summary"]

CHECKS = (
    "interview",
    "answers",
    "files",
    "settings",
    "hooks",
    "commands",
    "repo-checks",
    "repo-seeds",
    "commits",
    "prompts",
    "reviewer",
)
_GITCONFIG = "[user]\n\tname = Alpha Evals\n\temail = evals@example.com\n"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def prepare_kit(repo: Path, dest: Path) -> tuple[str, bool]:
    subprocess.run(
        ["git", "clone", "-q", "--no-hardlinks", str(repo), str(dest)],
        check=True,
        capture_output=True,
    )
    _git(dest, "remote", "remove", "origin")
    dirty = bool(_git(repo, "status", "--porcelain"))
    return _git(dest, "rev-parse", "HEAD"), dirty


def eval_env(run_dir: Path, kit: Path) -> dict[str, str]:
    config = run_dir / "gitconfig"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(_GITCONFIG, encoding="utf-8")
    return {
        **os.environ,
        "ALPHA_SOURCE": str(kit),
        "ALPHA_CONFIG_DIR": str(run_dir / "alpha-config"),
        "GIT_CONFIG_GLOBAL": str(config),
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def _safe(name: str, check: Callable[[], Check]) -> Check:
    try:
        return check()
    except Exception as e:  # noqa: BLE001 - one crashing check is reported, not fatal
        return Check(name, "fail", f"crashed: {type(e).__name__}: {e}")


def project_checks(project: Path, brief: Brief, scratch: Path) -> list[Check]:
    return [
        _safe("answers", lambda: check_answers(project, brief)),
        _safe("files", lambda: check_files(project)),
        _safe("settings", lambda: check_settings(project)),
        _safe("hooks", lambda: check_hooks(project, scratch)),
        _safe("commands", lambda: check_commands(project)),
        _safe("repo-checks", lambda: check_repo_checks(project)),
        _safe("repo-seeds", lambda: check_repo_seeds(project)),
        _safe("commits", lambda: check_commits(project)),
    ]


def _prompts(denials: Sequence[Mapping[str, Any]]) -> Check:
    if not denials:
        return Check("prompts", "pass")
    lines = [
        f"{d.get('tool_name')}: {json.dumps(d.get('tool_input'))[:120]}"
        for d in denials
    ]
    return Check("prompts", "warn", "\n".join(lines))


def _generated(project: Path) -> bool:
    try:
        return "manifest" in json.loads((project / PROJECT_JSON).read_text("utf-8"))
    except (OSError, ValueError, TypeError):
        return False


def run_scenario(
    name: str,
    run_dir: Path,
    kit: Path,
    env: Mapping[str, str],
    config: Config,
    reviewer: bool,
    kit_commit: str = "",
    kit_dirty: bool = False,
) -> dict[str, Any]:
    brief = load_brief(name)
    folder = run_dir / name
    folder.mkdir(parents=True)
    # Named like a user's own folder: a path with the scenario in it is a hint.
    project = run_dir / "projects" / str(brief.answers["identity"]["slug"])
    project.mkdir(parents=True)
    t = interview(brief, project, kit, env, config)
    (folder / "transcript.json").write_text(
        json.dumps(t.exchanges, indent=2, ensure_ascii=False) + "\n", "utf-8"
    )
    cost = t.cost_usd
    checks: list[Check] = [t.outcome]
    if t.outcome.status == "pass" and _generated(project):
        checks += project_checks(project, brief, folder)
    elif t.outcome.status == "pass":
        checks.append(Check("answers", "fail", f"{PROJECT_JSON} has no manifest"))
        checks += [Check(n, "skip", "interview did not finish") for n in CHECKS[2:9]]
    else:
        checks += [Check(n, "skip", "interview did not finish") for n in CHECKS[1:9]]
    checks.append(_prompts(t.denials))
    if not reviewer:
        checks.append(Check("reviewer", "skip", "--no-reviewer"))
    elif checks[1].status == "skip" or not _generated(project):
        checks.append(Check("reviewer", "skip", "interview did not finish"))
    else:
        try:
            found, turn = check_reviewer(project, env, config, config.max_usd - cost)
            cost += turn.cost_usd
        except Exception as e:  # noqa: BLE001 - a crashing probe is reported, not fatal
            found = Check("reviewer", "fail", f"crashed: {type(e).__name__}: {e}")
        checks.append(found)
    report: dict[str, Any] = {
        "scenario": name,
        "kit_commit": kit_commit,
        "kit_dirty": kit_dirty,
        "cost_usd": round(cost, 4),
        "exchanges": len(t.exchanges),
        "checks": [c.to_json() for c in checks],
    }
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", "utf-8")
    return report


def crashed_report(name: str, error: Exception) -> dict[str, Any]:
    detail = f"crashed: {type(error).__name__}: {error}"
    checks = [Check("interview", "fail", detail)] + [
        Check(n, "skip", "interview did not finish") for n in CHECKS[1:]
    ]
    return {
        "scenario": name,
        "cost_usd": 0.0,
        "exchanges": 0,
        "checks": [c.to_json() for c in checks],
    }


def summary(reports: Sequence[dict[str, Any]], kit_commit: str, kit_dirty: bool) -> str:
    lines = [f"# alpha interview evals (kit {kit_commit[:7]})", ""]
    if kit_dirty:
        lines += [
            "Warning: the kit checkout has uncommitted changes; these evals ran "
            f"HEAD {kit_commit[:7]}.",
            "",
        ]
    lines += [
        f"| scenario | {' | '.join(CHECKS)} | cost |",
        f"|---|{'---|' * len(CHECKS)}---|",
    ]
    problems: list[str] = []
    for r in reports:
        by_name = {c["name"]: c for c in r["checks"]}
        cells = [by_name[n]["status"] if n in by_name else "-" for n in CHECKS]
        lines.append(
            f"| {r['scenario']} | {' | '.join(cells)} | ${r['cost_usd']:.2f} |"
        )
        for c in r["checks"]:
            if c["status"] != "pass":
                first = (c["detail"].splitlines() or [""])[0]
                problems.append(
                    f"- {r['scenario']} / {c['name']} ({c['status']}): {first}"
                )
    if problems:
        lines += ["", "## Problems", "", *problems]
    return "\n".join(lines) + "\n"
