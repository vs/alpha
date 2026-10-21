import hashlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from helpers import TODAY, git, place_answers

from alpha import VERSION
from alpha.answers import AnswersError
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.generate import GenerateError, bootstrap, generate

ROOT = PLUGIN_ROOT
SRC = Source(ROOT, True, "")
SHIM = ROOT / "bin" / "alpha"
PROJECT_JSON = ".claude/alpha/project.json"


def run_cli(*args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, str(SHIM), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def test_refuses_non_empty_folder(tmp_path: Path):
    (tmp_path / "README.md").write_text("x")
    (tmp_path / ".DS_Store").write_text("")
    with pytest.raises(GenerateError, match=r"not empty \(found: README.md\)"):
        generate(tmp_path, ROOT, SRC, 2026)


def test_refusal_lists_offending_entries_sorted_with_a_fix(tmp_path: Path):
    place_answers(tmp_path, "python-ml-single")
    (tmp_path / "b.txt").write_text("x")
    (tmp_path / "a").mkdir()
    (tmp_path / ".claude" / "skills").mkdir()
    (tmp_path / ".claude" / "alpha" / "state").mkdir()
    with pytest.raises(GenerateError) as err:
        generate(tmp_path, ROOT, SRC, 2026)
    assert str(err.value) == (
        f"{tmp_path} is not empty (found: .claude/alpha/state, .claude/skills, a, "
        "b.txt). alpha v0.1 starts projects only in empty folders. Choose a new "
        "folder, or move these files out first."
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == [".claude", "a", "b.txt"]


def test_accepts_alpha_dir_ds_store_and_local_settings(tmp_path: Path):
    place_answers(tmp_path, "python-ml-single")
    (tmp_path / ".DS_Store").write_text("")
    (tmp_path / ".claude" / "settings.local.json").write_text("{}")
    files = generate(tmp_path, ROOT, SRC, 2026, TODAY)
    assert ".claude/settings.local.json" not in files
    assert ".DS_Store" not in files
    assert (tmp_path / ".claude" / "settings.local.json").read_text() == "{}"


def test_missing_answers_file_is_explained(tmp_path: Path):
    with pytest.raises(AnswersError, match="Run the alpha interview first"):
        generate(tmp_path, ROOT, SRC, 2026)
    assert list(tmp_path.iterdir()) == []


def source_head() -> str | None:
    done = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return done.stdout.strip() if done.returncode == 0 else None


def test_manifest_records_kit_defaults_and_hashes(
    tmp_path: Path, generate_scenario, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # ROOT is not under it
    original = json.loads(
        (ROOT / "evals/scenarios/web-ts-plus-python-api.json").read_text()
    )
    files = generate_scenario(tmp_path, "web-ts-plus-python-api")
    data = json.loads((tmp_path / PROJECT_JSON).read_text())
    m = data.pop("manifest")
    assert data == original  # the interview answers are preserved as they were
    assert list(data) == list(original)
    assert m["kit_version"] == VERSION
    assert m["generated_at"] == "2026-10-19"
    assert m["defaults"] == {"path": str(ROOT), "live": True, "commit": source_head()}
    assert list(m["files"]) == sorted(m["files"])
    assert set(m["files"]) == set(files) - {PROJECT_JSON}
    assert (tmp_path / PROJECT_JSON).read_text().endswith("}\n")


def test_manifest_abbreviates_the_home_directory(
    tmp_path: Path, generate_scenario, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HOME", str(ROOT.parent))
    generate_scenario(tmp_path, "python-ml-single")
    m = json.loads((tmp_path / PROJECT_JSON).read_text())["manifest"]
    assert m["defaults"]["path"] == f"~/{ROOT.name}"


def test_manifest_commit_is_null_for_bundled_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    place_answers(tmp_path, "python-ml-single")
    generate(tmp_path, ROOT, Source(ROOT, False, "no checkout"), 2026, TODAY)
    m = json.loads((tmp_path / PROJECT_JSON).read_text())["manifest"]
    assert m["defaults"] == {"path": str(ROOT), "live": False, "commit": None}


def test_gitignore_prefixes_component_paths(tmp_path: Path, generate_scenario):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    assert (tmp_path / ".gitignore").read_text() == (
        ".claude/alpha/state/\n"
        ".claude/settings.local.json\n"
        ".DS_Store\n"
        ".claude/alpha/hooks/__pycache__/\n"
        ".env\n"
        ".env.*\n"
        "**/.env\n"
        "**/.env.*\n"
        "!.env.example\n"
        "api/**/.venv/\n"
        "api/**/__pycache__/\n"
        "api/**/.pytest_cache/\n"
        "web/**/node_modules/\n"
        "web/**/dist/\n"
        "web/**/coverage/\n"
    )


def test_gitignore_for_root_component(tmp_path: Path, generate_scenario):
    generate_scenario(tmp_path, "python-ml-single")
    assert (tmp_path / ".gitignore").read_text() == (
        ".claude/alpha/state/\n"
        ".claude/settings.local.json\n"
        ".DS_Store\n"
        ".claude/alpha/hooks/__pycache__/\n"
        ".env\n"
        ".env.*\n"
        "**/.env\n"
        "**/.env.*\n"
        "!.env.example\n"
        ".venv/\n"
        "__pycache__/\n"
        ".pytest_cache/\n"
    )


@pytest.mark.parametrize(
    ("rel", "ignored"),
    [
        (".env", True),
        (".env.local", True),
        ("api/.env", True),
        ("api/.env.production", True),
        (".env.example", False),
        ("api/.env.example", False),
    ],
)
def test_gitignore_ignores_env_files_but_not_the_example(
    tmp_path: Path, generate_scenario, git_env, rel: str, ignored: bool
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    git(tmp_path, "init", "-q")
    done = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", rel], cwd=tmp_path
    )
    assert (done.returncode == 0) == ignored


def test_copies_hook_scripts_tools_and_executable_githook(
    tmp_path: Path, generate_scenario
):
    generate_scenario(tmp_path, "python-ml-single")
    hooks = tmp_path / ".claude/alpha/hooks"
    expected = sorted(p.name for p in (ROOT / "project-files/hooks").glob("*.py"))
    assert sorted(p.name for p in hooks.iterdir()) == expected
    for name in expected:
        source = ROOT / "project-files/hooks" / name
        assert (hooks / name).read_bytes() == source.read_bytes()
    githook = tmp_path / ".claude/alpha/githooks/commit-msg"
    assert (
        githook.read_bytes()
        == (ROOT / "project-files/githooks/commit-msg").read_bytes()
    )
    assert os.access(githook, os.X_OK)
    skill = tmp_path / ".claude/skills/commit/SKILL.md"
    assert (
        skill.read_text() == (ROOT / "project-files/skills/commit/SKILL.md").read_text()
    )
    agent = tmp_path / ".claude/agents/committer.md"
    assert agent.read_text() == (ROOT / "project-files/agents/committer.md").read_text()


def test_override_decision_file_matches_principles(tmp_path: Path, generate_scenario):
    files = generate_scenario(tmp_path, "web-ts-plus-python-api")
    principles = (tmp_path / "docs/principles.toml").read_text()
    path = "docs/decisions/0005-override-observability.md"
    assert path in files
    assert f'override_decision = "{path}"' in principles


def test_decision_records_carry_the_full_date(tmp_path: Path, generate_scenario):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    for record in sorted((tmp_path / "docs/decisions").glob("*.md")):
        assert "\nDate: 2026-10-19\n" in record.read_text(), record.name


def fake_tools(tmp_path: Path, exit_codes: dict[str, int]) -> Path:
    """Put logging stand-ins for uv and pnpm first on PATH."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    log = tmp_path / "tools.log"
    for tool in ("uv", "pnpm"):
        script = bin_dir / tool
        script.write_text(
            f'#!/bin/sh\necho "$(basename "$PWD"): {tool} $*" >> "{log}"\n'
            f'echo "{tool} output"\nexit {exit_codes.get(tool, 0)}\n'
        )
        script.chmod(0o755)
    return bin_dir


def test_bootstrap_runs_bootstrap_setup_test_per_component(
    tmp_path: Path,
    generate_scenario,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    project = tmp_path / "proj"
    project.mkdir()
    generate_scenario(project, "web-ts-plus-python-api")
    monkeypatch.setenv("PATH", f"{fake_tools(tmp_path, {})}:/usr/bin:/bin")
    bootstrap(project, tomllib.loads((project / "docs/principles.toml").read_text()))
    expected = [
        "api: uv add --dev pytest ruff pyright",
        "api: uv sync",
        "api: uv run pytest",
        "web: pnpm add -D typescript vitest @biomejs/biome @types/node",
        "web: pnpm install",
        "web: pnpm vitest run",
    ]
    assert (tmp_path / "tools.log").read_text().splitlines() == expected
    out = capsys.readouterr()
    assert out.err.splitlines() == [f"alpha: {line}" for line in expected]
    assert out.out == ""


def test_bootstrap_refreshes_the_manifest_hashes(
    tmp_path: Path, generate_scenario, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "proj"
    project.mkdir()
    generate_scenario(project, "web-ts-plus-python-api")
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    for tool, action in (("uv", "echo '# added' >> pyproject.toml"), ("pnpm", ":")):
        (bin_dir / tool).write_text(f"#!/bin/sh\n{action}\n")
        (bin_dir / tool).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    bootstrap(project, tomllib.loads((project / "docs/principles.toml").read_text()))
    files = json.loads((project / PROJECT_JSON).read_text())["manifest"]["files"]
    assert "api/pyproject.toml" in files
    for rel, digest in files.items():
        assert hashlib.sha256((project / rel).read_bytes()).hexdigest() == digest, rel


def test_bootstrap_failure_names_command_output_and_fix(
    tmp_path: Path, generate_scenario, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "proj"
    project.mkdir()
    generate_scenario(project, "web-ts-plus-python-api")
    monkeypatch.setenv("PATH", f"{fake_tools(tmp_path, {'pnpm': 3})}:/usr/bin:/bin")
    with pytest.raises(GenerateError) as err:
        bootstrap(
            project, tomllib.loads((project / "docs/principles.toml").read_text())
        )
    message = str(err.value)
    assert '"pnpm add -D typescript vitest @biomejs/biome @types/node"' in message
    assert "exit 3" in message
    assert "pnpm output" in message
    assert message.endswith(
        "Fix the toolchain (is uv/pnpm installed?) and rerun "
        f'"alpha bootstrap {project}"'
    )


def test_bootstrap_keeps_only_the_last_40_lines(
    tmp_path: Path, generate_scenario, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "proj"
    project.mkdir()
    generate_scenario(project, "python-ml-single")
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text('#!/bin/sh\nfor i in $(seq 1 100); do echo "line $i"; done\nexit 1\n')
    uv.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    with pytest.raises(GenerateError) as err:
        bootstrap(
            project, tomllib.loads((project / "docs/principles.toml").read_text())
        )
    message = str(err.value)
    assert "line 61\n" in message and "line 100\n" in message
    assert "line 60\n" not in message


def test_cli_generate_prints_summary(tmp_path: Path):
    place_answers(tmp_path, "python-ml-single")
    out = run_cli("generate", str(tmp_path), env={"ALPHA_SOURCE": str(ROOT)})
    assert out.returncode == 0, out.stderr
    assert "Generated" in out.stdout and str(tmp_path) in out.stdout
    assert out.stderr == ""
    assert (tmp_path / "CLAUDE.md").is_file()


def test_cli_generate_warns_when_defaults_are_bundled(tmp_path: Path):
    project = tmp_path / "proj"
    place_answers(project, "python-ml-single")
    env = {k: v for k, v in os.environ.items() if k != "ALPHA_SOURCE"}
    env["HOME"] = str(tmp_path / "home")
    out = subprocess.run(
        [sys.executable, str(SHIM), "generate", str(project)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert out.returncode == 0, out.stderr
    assert "bundled kit defaults" in out.stderr
    assert "no alpha source checkout found" in out.stderr


def test_cli_generate_error_exits_1(tmp_path: Path):
    (tmp_path / "README.md").write_text("x")
    out = run_cli("generate", str(tmp_path), env={"ALPHA_SOURCE": str(ROOT)})
    assert out.returncode == 1
    assert "is not empty (found: README.md)" in out.stderr


def test_cli_bootstrap_without_principles_exits_1(tmp_path: Path):
    out = run_cli("bootstrap", str(tmp_path))
    assert out.returncode == 1
    assert "docs/principles.toml" in out.stderr
    assert "alpha generate" in out.stderr


def test_cli_commit_skeleton_with_trailers(tmp_path: Path, generate_scenario, git_env):
    generate_scenario(tmp_path, "python-ml-single")
    out = run_cli(
        "commit-skeleton", str(tmp_path), "--trailer", "A: b", "--trailer", "C: d"
    )
    assert out.returncode == 0, out.stderr
    assert "build(ml): Set up python toolchain and tests" in out.stdout
    body = subprocess.run(
        ["git", "log", "-1", "--format=%B"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert body.endswith("\n\nA: b\nC: d")


def test_answers_still_load_after_the_manifest_is_added(
    tmp_path: Path, generate_scenario
):
    generate_scenario(tmp_path, "web-ts-plus-python-api")
    out = run_cli("answers", "check", str(tmp_path / PROJECT_JSON))
    assert out.returncode == 0, out.stderr


def edit_principles(target: Path, edit) -> None:
    from alpha.principles import render_principles

    path = target / "docs/principles.toml"
    data = tomllib.loads(path.read_text())
    edit(data)
    path.write_text(render_principles(data))


def assert_explained(out: subprocess.CompletedProcess[str], *needles: str) -> None:
    assert out.returncode == 1
    assert "Traceback" not in out.stderr
    for needle in needles:
        assert needle in out.stderr


def test_cli_bootstrap_explains_unknown_stack(tmp_path: Path, generate_scenario):
    generate_scenario(tmp_path, "python-ml-single")
    edit_principles(tmp_path, lambda d: d["components"][0].update(stack="rust"))
    out = run_cli("bootstrap", str(tmp_path))
    assert_explained(
        out, 'No recipe for stack "rust"', "Use one of: python, typescript"
    )


def test_cli_bootstrap_explains_missing_principles_key(
    tmp_path: Path, generate_scenario
):
    generate_scenario(tmp_path, "python-ml-single")
    edit_principles(tmp_path, lambda d: d["components"][0]["commands"].pop("setup"))
    out = run_cli("bootstrap", str(tmp_path))
    assert_explained(
        out,
        "docs/principles.toml is missing 'setup'",
        "git checkout docs/principles.toml",
    )


def test_cli_generate_explains_write_failure(tmp_path: Path):
    project = tmp_path / "proj"
    place_answers(project, "python-ml-single")
    project.chmod(0o555)  # docs/ cannot be created
    try:
        out = run_cli("generate", str(project), env={"ALPHA_SOURCE": str(ROOT)})
    finally:
        project.chmod(0o755)
    assert_explained(out, f"Could not write {project / 'docs'}", "permissions")
