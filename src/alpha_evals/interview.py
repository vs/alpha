from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alpha_evals.checks import Check
from alpha_evals.claude import Turn, run_claude
from alpha_evals.scenario import Brief

END = "<<END>>"
USER_SYSTEM = "\n".join(
    [
        (
            "You are playing a person who is starting a new software project with an AI"
            " assistant that interviews you. Your notes about the project follow. Reply"
            " as that person, briefly and in plain text."
        ),
        (
            "- Answer only what the assistant asks, from your notes. Never invent "
            "requirements, names or tools your notes don't give."
        ),
        (
            "- When the assistant offers a recommendation or default and your notes "
            "don't settle the question, accept it."
        ),
        (
            "- When the assistant shows a summary and asks to go ahead, check it "
            "against your notes, correct anything that differs, and otherwise say yes."
        ),
        (
            "- When asked to allow or approve something the assistant needs to proceed,"
            " say yes."
        ),
        "- Never write code or files yourself.",
        (
            "- When the assistant says the project is generated and committed and asks "
            "nothing more, or when it is plainly stuck and repeating itself, reply with"
            " exactly <<END>>."
        ),
    ]
)


@dataclass(frozen=True)
class Config:
    claude: tuple[str, ...] = ("claude",)
    interviewer_model: str = "opus"
    user_model: str = "sonnet"
    max_exchanges: int = 60
    max_usd: float = 20.0


@dataclass
class Transcript:
    exchanges: list[dict[str, Any]]
    cost_usd: float
    denials: list[dict[str, Any]]
    outcome: Check


def interviewer_args(kit: Path, config: Config) -> list[str]:
    return [
        "--plugin-dir",
        str(kit),
        "--model",
        config.interviewer_model,
        "--permission-mode",
        "auto",
        "--allowedTools",
        f"Bash({kit}/bin/alpha *)",
        "Read",
        "Glob",
        "Grep",
        "Skill",
        "WebSearch",
        "WebFetch",
    ]


def interview(
    brief: Brief, project: Path, kit: Path, env: Mapping[str, str], config: Config
) -> Transcript:
    t = Transcript([], 0.0, [], Check("interview", "fail", "not started"))
    user_args = [
        "--model",
        config.user_model,
        "--tools",
        "",
        "--system-prompt",
        f"{USER_SYSTEM}\n\n{brief.text}",
    ]
    sessions: dict[str, str | None] = {"assistant": None, "user": None}

    def call(role: str, prompt: str) -> Turn | None:
        if t.cost_usd >= config.max_usd:
            t.outcome = Check(
                "interview", "fail", f"budget of ${config.max_usd:g} reached"
            )
            return None
        if role == "assistant":
            args, cwd = interviewer_args(kit, config), project
        else:
            args, cwd = user_args, project.parent
        budget = ["--max-budget-usd", f"{config.max_usd - t.cost_usd:.2f}"]
        turn = run_claude(
            config.claude, [*args, *budget], prompt, cwd, env, sessions[role]
        )
        t.cost_usd += turn.cost_usd
        if not turn.ok:
            t.outcome = Check("interview", "fail", f"{role} call failed: {turn.error}")
            return None
        sessions[role] = turn.session_id or sessions[role]
        t.exchanges.append({"role": role, "text": turn.text, "cost_usd": turn.cost_usd})
        if role == "assistant":
            t.denials.extend(turn.denials)
        return turn

    prompt = f"/alpha:new-project {project}"
    for _ in range(config.max_exchanges):
        asked = call("assistant", prompt)
        if asked is None:
            return t
        answered = call("user", asked.text)
        if answered is None:
            return t
        if answered.text.strip().endswith(END):
            t.outcome = Check("interview", "pass")
            return t
        prompt = answered.text
    t.outcome = Check(
        "interview", "fail", f"stopped after {config.max_exchanges} exchanges"
    )
    return t
