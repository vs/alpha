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
