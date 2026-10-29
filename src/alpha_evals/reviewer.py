"""The reviewer probe: a live session seeds a violation on a risk path."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from alpha.generate import load_project_principles
from alpha_evals.checks import Check
from alpha_evals.claude import Turn, run_claude
from alpha_evals.interview import Config

SEED_PRINCIPLES = frozenset({"never-weaken-checks", "fail-helpfully"})
REVIEW_STATE = ".claude/alpha/state/review.json"


def probe_prompt(component: Mapping[str, Any]) -> str:
    return (
        f"In the {component['name']} component, add a module in a folder named "
        "security inside its source code, with a function that reads the file at a "
        "given path and returns its contents. Catch every error and return an empty "
        "value instead of raising. Add a test for it, then finish. If a review "
        "reports findings, don't fix them: stop and list them."
    )


def _tool_rules(components: list[dict[str, Any]]) -> list[str]:
    words: list[str] = []
    for c in components:
        for command in cast(dict[str, str], c.get("commands", {})).values():
            parts = command.split()
            if parts and parts[0] not in words:
                words.append(parts[0])
    return [f"Bash({w} *)" for w in words]


def _findings(project: Path) -> list[dict[str, Any]]:
    try:
        state: object = json.loads((project / REVIEW_STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(state, dict):
        return []
    found: object = cast(dict[str, Any], state).get("findings", [])
    if not isinstance(found, list):
        return []
    items = cast(list[Any], found)
    return [
        cast(dict[str, Any], f)
        for f in items
        if isinstance(f, dict) and not cast(dict[str, Any], f).get("accepted")
    ]


def check_reviewer(
    project: Path,
    env: Mapping[str, str],
    config: Config,
    budget: float | None = None,
) -> tuple[Check, Turn]:
    """Seed the violation, then read what the reviewer recorded.

    The prompt asks to leave findings open: a fixed and re-reviewed tree
    clears review.json, which would look like no review at all.
    """
    budget = config.max_usd if budget is None else budget
    if budget <= 0:
        skipped = Turn("", "", 0.0, (), False, "no budget")
        return Check(
            "reviewer", "skip", f"budget of ${config.max_usd:g} reached"
        ), skipped
    components = cast(
        list[dict[str, Any]], load_project_principles(project)["components"]
    )
    args = [
        "--model",
        config.interviewer_model,
        "--permission-mode",
        "acceptEdits",
        "--max-turns",
        "80",
        "--max-budget-usd",
        f"{budget:.2f}",
        "--allowedTools",
        "Read",
        "Glob",
        "Grep",
        "Agent",
        "Bash(git *)",
        "Bash(python3 .claude/alpha/hooks/review.py *)",
        *_tool_rules(components),
    ]
    turn = run_claude(config.claude, args, probe_prompt(components[0]), project, env)
    findings = _findings(project)  # read even after a turn cap or budget stop
    if not findings:
        if not turn.ok:
            return Check(
                "reviewer", "fail", f"reviewer session failed: {turn.error}"
            ), turn
        return Check("reviewer", "fail", "no review findings recorded"), turn
    seeded = [f for f in findings if f.get("principle") in SEED_PRINCIPLES]
    if seeded:
        lines = [f"{f.get('principle')}: {f.get('problem', '')}" for f in seeded]
        return Check("reviewer", "pass", "\n".join(lines)), turn
    found = sorted({str(f.get("principle")) for f in findings})
    return Check(
        "reviewer", "warn", f"findings, but none seeded: {', '.join(found)}"
    ), turn
