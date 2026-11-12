import os
from pathlib import Path
from typing import Any

from alpha_evals.claude import run_claude
from alpha_evals.interview import Config, interview
from alpha_evals.scenario import load_brief

from .conftest import FakeClaude

BRIEF = load_brief("python-ml-single")


def project_in(tmp_path: Path) -> Path:
    project = tmp_path / "run" / "project"
    project.mkdir(parents=True)
    return project


def go(fake: FakeClaude, tmp_path: Path, **config: Any):
    project = project_in(tmp_path)
    kit = tmp_path / "kit"
    cfg = Config(claude=fake.command, **config)
    return project, kit, interview(BRIEF, project, kit, dict(os.environ), cfg)


def arg_after(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def test_loop_alternates_and_ends_on_the_token(fake: FakeClaude, tmp_path: Path):
    fake.reply("Q1?", session="s-int")
    fake.reply("A1", session="s-user")
    fake.reply("Done, committed.", session="s-int")
    fake.reply("All good. <<END>>", session="s-user")
    project, kit, t = go(fake, tmp_path)
    assert (t.outcome.name, t.outcome.status) == ("interview", "pass")
    assert [e["role"] for e in t.exchanges] == [
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert t.exchanges[0]["text"] == "Q1?"
    assert round(t.cost_usd, 2) == 0.04
    first, user1, int2, user2 = fake.calls()
    assert first["stdin"] == f"/alpha:new-project {project}"
    assert first["cwd"] == str(project)
    assert arg_after(first["argv"], "--plugin-dir") == str(kit)
    assert arg_after(first["argv"], "--permission-mode") == "auto"
    assert arg_after(first["argv"], "--setting-sources") == "project,local"
    assert f"Bash({kit}/bin/alpha *)" in first["argv"]
    assert "--resume" not in first["argv"]
    assert arg_after(user1["argv"], "--tools") == ""
    assert BRIEF.text in arg_after(user1["argv"], "--system-prompt")
    assert user1["cwd"] == str(project.parent)
    assert user1["stdin"] == "Q1?"
    assert "--resume" not in user1["argv"]
    assert arg_after(int2["argv"], "--resume") == "s-int"
    assert int2["stdin"] == "A1"
    assert arg_after(user2["argv"], "--resume") == "s-user"


def test_a_failed_call_stops_with_its_stderr(fake: FakeClaude, tmp_path: Path):
    fake.fail(exit=1, stderr="auth expired\n")
    _, _, t = go(fake, tmp_path)
    assert t.outcome.status == "fail"
    assert "assistant call failed: exit 1: auth expired" in t.outcome.detail


def test_a_failed_user_call_names_the_user(fake: FakeClaude, tmp_path: Path):
    fake.reply("Q1?")
    fake.fail(exit=3, stderr="rate limited")
    _, _, t = go(fake, tmp_path)
    assert "user call failed: exit 3: rate limited" in t.outcome.detail


def test_non_json_output_is_a_failure_not_a_crash(fake: FakeClaude, tmp_path: Path):
    fake.fail(exit=0, stdout="oops")
    _, _, t = go(fake, tmp_path)
    assert t.outcome.status == "fail"
    assert "not JSON: oops" in t.outcome.detail


def test_an_error_result_is_a_failure(fake: FakeClaude, tmp_path: Path):
    fake.add(
        {
            "stdout": {
                "subtype": "error_max_turns",
                "is_error": True,
                "result": "",
                "session_id": "s",
                "total_cost_usd": 0.5,
            }
        }
    )
    _, _, t = go(fake, tmp_path)
    assert t.outcome.status == "fail"
    assert "error_max_turns" in t.outcome.detail
    assert t.cost_usd == 0.5


def test_exchange_cap_stops_a_looping_interview(fake: FakeClaude, tmp_path: Path):
    for _ in range(3):
        fake.reply("Same question?")
        fake.reply("Same answer")
    _, _, t = go(fake, tmp_path, max_exchanges=2)
    assert t.outcome.status == "fail"
    assert t.outcome.detail == "stopped after 2 exchanges"
    assert len(t.exchanges) == 4


def test_budget_stops_before_the_next_call(fake: FakeClaude, tmp_path: Path):
    for _ in range(3):
        fake.reply("Q?", cost=0.03)
        fake.reply("A", cost=0.03)
    _, _, t = go(fake, tmp_path, max_usd=0.05)
    assert t.outcome.status == "fail"
    assert t.outcome.detail == "budget of $0.05 reached"
    assert len(fake.calls()) == 2


def test_denials_are_collected(fake: FakeClaude, tmp_path: Path):
    denial = {"tool_name": "Bash", "tool_input": {"command": "python3 -"}}
    fake.reply("Q1?", denials=[denial])
    fake.reply("<<END>>")
    _, _, t = go(fake, tmp_path)
    assert t.denials == [denial]


def test_run_claude_reports_a_timeout(tmp_path: Path):
    turn = run_claude(
        ("sh", "-c", "sleep 5", "claude"),
        [],
        "",
        tmp_path,
        dict(os.environ),
        timeout=0.2,
    )
    assert not turn.ok
    assert turn.error == "timeout after 0.2s"


def test_run_claude_reports_a_missing_binary(tmp_path: Path):
    turn = run_claude(("no-such-claude-x",), [], "", tmp_path, dict(os.environ))
    assert not turn.ok
    assert "no-such-claude-x" in turn.error


def test_a_failed_json_result_keeps_its_reason_and_cost(
    fake: FakeClaude, tmp_path: Path
):
    fake.add(
        {
            "stdout": {
                "subtype": "success",
                "is_error": True,
                "result": "Invalid API key",
                "session_id": "s",
                "total_cost_usd": 0.02,
            },
            "exit": 1,
        }
    )
    _, _, t = go(fake, tmp_path)
    assert "Invalid API key" in t.outcome.detail
    assert t.cost_usd == 0.02


def test_a_failure_reported_on_stdout_is_shown(fake: FakeClaude, tmp_path: Path):
    fake.fail(exit=1, stdout="Rate limited, retry later")
    _, _, t = go(fake, tmp_path)
    assert "Rate limited, retry later" in t.outcome.detail


def test_each_call_gets_the_remaining_budget(fake: FakeClaude, tmp_path: Path):
    fake.reply("Q?", cost=0.25)
    fake.reply("<<END>>", cost=0.5)
    go(fake, tmp_path, max_usd=2)
    first, second = fake.calls()
    assert arg_after(first["argv"], "--max-budget-usd") == "2.00"
    assert arg_after(second["argv"], "--max-budget-usd") == "1.75"
