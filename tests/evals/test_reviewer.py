import json
import os
from pathlib import Path

from helpers import generated_repo

from alpha_evals.interview import Config
from alpha_evals.reviewer import check_reviewer, probe_prompt

STATE = ".claude/alpha/state/review.json"


def write_state(findings: list[dict]) -> str:
    text = json.dumps({"findings": findings}).replace("'", "'\\''")
    return f"mkdir -p .claude/alpha/state && printf '%s' '{text}' > {STATE}"


def probe(fake, tmp_path: Path, findings: list[dict] | None):
    project = generated_repo(tmp_path / "p", "web-ts-plus-python-api")
    run = None if findings is None else write_state(findings)
    fake.reply("Done.", run=run)
    check, turn = check_reviewer(project, dict(os.environ), Config(claude=fake.command))
    return project, check, turn


def test_prompt_names_the_component():
    assert probe_prompt({"name": "api"}).startswith("In the api component,")


def test_seeded_finding_passes(fake, tmp_path: Path, git_env):
    finding = {
        "id": "F-1",
        "principle": "fail-helpfully",
        "problem": "errors become b''",
    }
    project, check, turn = probe(fake, tmp_path, [finding])
    assert (check.name, check.status) == ("reviewer", "pass")
    assert "fail-helpfully: errors become b''" in check.detail
    assert turn.ok
    (call,) = fake.calls()
    assert call["cwd"] == str(project)
    assert call["stdin"] == probe_prompt({"name": "api"})
    assert "--plugin-dir" not in call["argv"]
    assert "Bash(uv *)" in call["argv"] and "Bash(pnpm *)" in call["argv"]
    assert call["argv"].count("Bash(uv *)") == 1
    assert call["argv"][call["argv"].index("--permission-mode") + 1] == "acceptEdits"


def test_other_findings_warn(fake, tmp_path: Path, git_env):
    finding = {"id": "F-1", "principle": "docs-match-code", "problem": "x"}
    _, check, _ = probe(fake, tmp_path, [finding])
    assert check.status == "warn"
    assert "docs-match-code" in check.detail


def test_accepted_findings_do_not_count(fake, tmp_path: Path, git_env):
    finding = {
        "id": "F-1",
        "principle": "fail-helpfully",
        "problem": "x",
        "accepted": True,
    }
    _, check, _ = probe(fake, tmp_path, [finding])
    assert check.status == "fail"
    assert check.detail == "no review findings recorded"


def test_no_state_fails(fake, tmp_path: Path, git_env):
    _, check, _ = probe(fake, tmp_path, None)
    assert (check.status, check.detail) == ("fail", "no review findings recorded")


def test_a_failed_session_fails(fake, tmp_path: Path, git_env):
    project = generated_repo(tmp_path / "p", "web-ts-plus-python-api")
    fake.fail(exit=1, stderr="boom")
    check, _ = check_reviewer(project, dict(os.environ), Config(claude=fake.command))
    assert check.status == "fail"
    assert check.detail == "reviewer session failed: exit 1: boom"


def test_prompt_asks_to_leave_findings_open():
    assert "If a review reports findings, don't fix them" in probe_prompt(
        {"name": "api"}
    )


def test_findings_count_even_when_the_session_hits_its_turn_cap(
    fake, tmp_path: Path, git_env
):
    project = generated_repo(tmp_path / "p", "web-ts-plus-python-api")
    finding = {"id": "F-1", "principle": "never-weaken-checks", "problem": "catch-all"}
    fake._add(
        {
            "stdout": {
                "subtype": "error_max_turns",
                "is_error": True,
                "result": "",
                "session_id": "s",
                "total_cost_usd": 1.0,
            },
            "run": write_state([finding]),
        }
    )
    check, _ = check_reviewer(project, dict(os.environ), Config(claude=fake.command))
    assert check.status == "pass"


def test_reviewer_gets_the_remaining_budget(fake, tmp_path: Path, git_env):
    project = generated_repo(tmp_path / "p", "web-ts-plus-python-api")
    fake.reply("Done.")
    check_reviewer(project, dict(os.environ), Config(claude=fake.command), budget=3.456)
    argv = fake.calls()[0]["argv"]
    assert argv[argv.index("--max-budget-usd") + 1] == "3.46"


def test_no_budget_left_skips_the_probe(fake, tmp_path: Path, git_env):
    project = generated_repo(tmp_path / "p", "web-ts-plus-python-api")
    check, _ = check_reviewer(
        project, dict(os.environ), Config(claude=fake.command, max_usd=5), budget=0
    )
    assert (check.status, check.detail) == ("skip", "budget of $5 reached")
    assert fake.calls() == []
