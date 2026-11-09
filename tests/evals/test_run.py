import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import SCENARIOS, generated_repo, git

from alpha_evals import run
from alpha_evals.__main__ import main
from alpha_evals.run import eval_env, prepare_kit, summary

ORDER = [
    "interview",
    "answers",
    "files",
    "settings",
    "hooks",
    "commands",
    "commits",
    "prompts",
    "reviewer",
]


def fake_interview(fake, scenario: str) -> None:
    answers = shlex.quote(str(SCENARIOS / f"{scenario}.json"))
    fake.reply(
        "Generated and committed.",
        session="s-int",
        run=(
            f"mkdir -p .claude/alpha && cp {answers} .claude/alpha/project.json"
            ' && "$ALPHA_SOURCE/bin/alpha" generate "$PWD" >/dev/null'
            ' && "$ALPHA_SOURCE/bin/alpha" commit-skeleton "$PWD" >/dev/null'
        ),
    )
    fake.reply("<<END>>", session="s-user")


def run_args(fake, out: Path, *more: str) -> list[str]:
    return ["run", *more, "--out", str(out), "--claude", shlex.join(fake.command)]


def report_of(out: Path, scenario: str) -> dict:
    return json.loads((out / scenario / "report.json").read_text())


def test_offline_run_writes_a_passing_report(fake, tmp_path: Path, git_env, stub_tools):
    fake_interview(fake, "python-ml-single")
    out = tmp_path / "out"
    assert main(run_args(fake, out, "python-ml-single", "--no-reviewer")) == 0
    report = report_of(out, "python-ml-single")
    statuses = {c["name"]: c["status"] for c in report["checks"]}
    assert [c["name"] for c in report["checks"]] == ORDER
    assert statuses == {**dict.fromkeys(ORDER, "pass"), "reviewer": "skip"}, report
    assert report["scenario"] == "python-ml-single"
    assert report["exchanges"] == 2
    assert report["kit_commit"] == git(Path(run.PLUGIN_ROOT), "rev-parse", "HEAD")
    transcript = json.loads((out / "python-ml-single/transcript.json").read_text())
    assert transcript[-1]["text"] == "<<END>>"
    text = (out / "summary.md").read_text()
    assert "| python-ml-single | pass |" in text


def test_unfinished_interview_skips_the_checks(fake, tmp_path: Path, git_env):
    fake.fail(exit=1, stderr="auth expired")
    out = tmp_path / "out"
    assert main(run_args(fake, out, "rust-cli")) == 1
    checks = report_of(out, "rust-cli")["checks"]
    assert checks[0]["status"] == "fail"
    for c in checks[1:]:
        if c["name"] == "prompts":
            continue
        assert (c["status"], c["detail"]) == ("skip", "interview did not finish")


def test_a_crashing_check_is_recorded(
    monkeypatch: pytest.MonkeyPatch, fake, tmp_path: Path, git_env, stub_tools
):
    def boom(project):
        raise RuntimeError("bad")

    monkeypatch.setattr(run, "check_files", boom)
    fake_interview(fake, "python-ml-single")
    out = tmp_path / "out"
    assert main(run_args(fake, out, "python-ml-single", "--no-reviewer")) == 1
    checks = {c["name"]: c for c in report_of(out, "python-ml-single")["checks"]}
    assert checks["files"]["status"] == "fail"
    assert checks["files"]["detail"] == "crashed: RuntimeError: bad"
    assert checks["commits"]["status"] == "pass"


def test_denials_become_a_prompts_warning(fake, tmp_path: Path, git_env):
    denial = {"tool_name": "Bash", "tool_input": {"command": "python3 - <<EOF"}}
    fake.reply("Q?", denials=[denial])
    fake.fail(exit=1, stderr="x")
    out = tmp_path / "out"
    main(run_args(fake, out, "rust-cli"))
    checks = {c["name"]: c for c in report_of(out, "rust-cli")["checks"]}
    assert checks["prompts"]["status"] == "warn"
    assert checks["prompts"]["detail"].startswith(
        'Bash: {"command": "python3 - <<EOF"}'
    )


def test_summary_warns_about_a_dirty_kit():
    text = summary([], "abc1234def", True)
    line = (
        "Warning: the kit checkout has uncommitted changes; "
        "these evals ran HEAD abc1234."
    )
    assert line in text


def test_summary_lists_the_problems():
    report = {
        "scenario": "rust-cli",
        "cost_usd": 1.234,
        "checks": [
            {"name": "interview", "status": "pass", "detail": ""},
            {"name": "answers", "status": "fail", "detail": "/layout: x\n/y: z"},
        ],
    }
    text = summary([report], "abc1234def", False)
    assert "Warning" not in text
    assert "| rust-cli | pass | fail |" in text
    assert "$1.23" in text
    assert "- rust-cli / answers (fail): /layout: x" in text


def test_prepare_kit_reports_dirty_state(tmp_path: Path, git_env):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("a\n")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-qm", "first")
    assert prepare_kit(repo, tmp_path / "c1")[1] is False
    (repo / "stray.txt").write_text("x\n")
    sha, dirty = prepare_kit(repo, tmp_path / "c2")
    assert dirty is True
    assert sha == git(repo, "rev-parse", "HEAD")
    assert (tmp_path / "c2/a.txt").is_file()
    assert not (tmp_path / "c2/stray.txt").exists()


def test_eval_env_isolates_git(tmp_path: Path):
    env = eval_env(tmp_path, tmp_path / "kit")
    assert env["ALPHA_SOURCE"] == str(tmp_path / "kit")
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == str(tmp_path / "gitconfig")
    config = (tmp_path / "gitconfig").read_text()
    assert "name = Alpha Evals" in config
    assert "email = evals@example.com" in config


def test_unknown_scenario_exits_2(capsys: pytest.CaptureFixture[str]):
    assert main(["run", "nope"]) == 2
    assert "python-ml-single" in capsys.readouterr().err


def test_check_subcommand_on_a_generated_project(
    tmp_path: Path, git_env, stub_tools, capsys: pytest.CaptureFixture[str]
):
    project = generated_repo(tmp_path / "p", "web-ts-plus-python-api")
    assert main(["check", str(project), "web-ts-plus-python-api"]) == 0
    out = capsys.readouterr().out
    assert "answers: pass" in out
    assert "hooks: pass" in out


def test_shim_runs_the_cli():
    done = subprocess.run(
        [sys.executable, str(Path(run.PLUGIN_ROOT) / "bin/alpha-evals"), "run", "nope"],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 2, done.stderr
    assert "Choose from" in done.stderr


def test_a_relative_out_becomes_absolute(
    fake, tmp_path: Path, git_env, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    fake.fail(exit=1, stderr="x")
    main(["run", "rust-cli", "--out", "out", "--claude", shlex.join(fake.command)])
    argv = fake.calls()[0]["argv"]
    plugin_dir = Path(argv[argv.index("--plugin-dir") + 1])
    assert plugin_dir == tmp_path / "out" / "kit"
    assert (
        fake.calls()[0]["stdin"] == f"/alpha:new-project {tmp_path}/out/projects/tidy"
    )


def test_a_run_folder_inside_the_kit_is_refused(
    fake, capsys: pytest.CaptureFixture[str]
):
    inside = Path(run.PLUGIN_ROOT) / ".superpowers" / "eval-run"
    assert main(run_args(fake, inside, "rust-cli")) == 2
    assert "outside" in capsys.readouterr().err
    assert not inside.exists()
    assert fake.calls() == []


def test_the_kit_clone_has_no_remote(tmp_path: Path, git_env):
    prepare_kit(Path(run.PLUGIN_ROOT), tmp_path / "kit")
    assert git(tmp_path / "kit", "remote") == ""


def test_a_crashing_reviewer_is_recorded(
    monkeypatch: pytest.MonkeyPatch, fake, tmp_path: Path, git_env, stub_tools
):
    def boom(*args, **kwargs):
        raise RuntimeError("bad principles")

    monkeypatch.setattr(run, "check_reviewer", boom)
    fake_interview(fake, "python-ml-single")
    out = tmp_path / "out"
    assert main(run_args(fake, out, "python-ml-single")) == 1
    checks = {c["name"]: c for c in report_of(out, "python-ml-single")["checks"]}
    assert checks["reviewer"]["status"] == "fail"
    assert checks["reviewer"]["detail"] == "crashed: RuntimeError: bad principles"


def test_a_crashing_scenario_does_not_stop_the_run(
    monkeypatch: pytest.MonkeyPatch, fake, tmp_path: Path, git_env
):
    import alpha_evals.__main__ as cli

    real = cli.run_scenario

    def flaky(name, *args, **kwargs):
        if name == "rust-cli":
            raise RuntimeError("disk full")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(cli, "run_scenario", flaky)
    fake.fail(exit=1, stderr="x")
    out = tmp_path / "out"
    assert main(run_args(fake, out, "rust-cli", "python-ml-single")) == 1
    text = (out / "summary.md").read_text()
    assert "| rust-cli | fail |" in text
    assert "rust-cli / interview (fail): crashed: RuntimeError: disk full" in text
    assert "| python-ml-single | fail |" in text
