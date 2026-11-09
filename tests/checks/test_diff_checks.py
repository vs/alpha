import importlib.util
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import git

SCRIPT = Path(__file__).parents[2] / "project-files" / "checks" / "diff_checks.py"
PRINCIPLES = (
    '[data]\nmigration_paths = ["migrations/**"]\nsquawk_paths = ["migrations/**"]\n'
)


@pytest.fixture
def repo(tmp_path: Path, git_env: None) -> Path:
    r = tmp_path / "repo"
    (r / "migrations").mkdir(parents=True)
    (r / "docs").mkdir()
    (r / "docs" / "principles.toml").write_text(PRINCIPLES)
    (r / "migrations" / "0001.sql").write_text("create table a (id int);\n")
    git(r, "init", "-q", "-b", "main")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "base")
    git(r, "checkout", "-q", "-b", "feature")
    return r


@pytest.fixture
def fake_squawk(tmp_path: Path) -> tuple[Path, Path]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "squawk.log"
    exe = bindir / "squawk"
    exe.write_text(f'#!/bin/sh\necho "$@" > "{log}"\nexit 0\n')
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return bindir, log


def run(
    repo: Path,
    check: str,
    base: str | None = "main",
    body: str = "",
    path: str | None = None,
):
    env = {k: v for k, v in os.environ.items() if k not in ("ALPHA_BASE", "PR_BODY")}
    if base is not None:
        env["ALPHA_BASE"] = base
    env["PR_BODY"] = body
    if path:
        env["PATH"] = path + os.pathsep + env["PATH"]
    return subprocess.run(
        [sys.executable, str(SCRIPT), check],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def commit(repo: Path) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")


@pytest.mark.parametrize("check", ["immutable-migrations", "squawk"])
@pytest.mark.parametrize("base", [None, "", "origin/nope"])
def test_diff_checks_without_base_skip(repo: Path, check: str, base: str | None):
    result = run(repo, check, base=base)
    assert result.returncode == 0
    assert "skipped" in result.stdout


def test_modified_migration_fails(repo: Path):
    (repo / "migrations" / "0001.sql").write_text("create table b (id int);\n")
    commit(repo)
    result = run(repo, "immutable-migrations")
    assert result.returncode == 1
    out = result.stdout + result.stderr
    assert "migrations/0001.sql" in out
    assert "git checkout" in out
    assert "alpha: migration edit approved" in out


def test_deleted_migration_fails(repo: Path):
    (repo / "migrations" / "0001.sql").unlink()
    commit(repo)
    assert run(repo, "immutable-migrations").returncode == 1


def test_new_migration_passes(repo: Path):
    (repo / "migrations" / "0002.sql").write_text("create table c (id int);\n")
    commit(repo)
    assert run(repo, "immutable-migrations").returncode == 0


def test_escape_marker_passes(repo: Path):
    (repo / "migrations" / "0001.sql").write_text("x\n")
    commit(repo)
    body = "Fixes a typo.\nalpha: migration edit approved\n"
    result = run(repo, "immutable-migrations", body=body)
    assert result.returncode == 0
    assert "approved" in result.stdout


def test_squawk_gets_only_added_sql(repo: Path, fake_squawk: tuple[Path, Path]):
    bindir, log = fake_squawk
    (repo / "migrations" / "0001.sql").write_text("changed\n")
    (repo / "migrations" / "0002.sql").write_text("create table c (id int);\n")
    (repo / "migrations" / "notes.md").write_text("hi\n")
    (repo / "other.sql").write_text("select 1;\n")
    commit(repo)
    result = run(repo, "squawk", path=str(bindir))
    assert result.returncode == 0
    assert log.read_text().split() == ["migrations/0002.sql"]


def test_squawk_without_added_files_exits_zero(repo: Path):
    assert run(repo, "squawk").returncode == 0


def test_squawk_missing_binary_fails_helpfully(repo: Path, tmp_path: Path):
    (repo / "migrations" / "0002.sql").write_text("select 1;\n")
    commit(repo)
    env = {k: v for k, v in os.environ.items()}
    env["ALPHA_BASE"] = "main"
    only_git = tmp_path / "only-git"
    only_git.mkdir()
    (only_git / "git").symlink_to(shutil.which("git") or "git")
    env["PATH"] = str(only_git)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "squawk"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert "mise install" in result.stdout + result.stderr


def test_git_error_fails_closed(repo: Path):
    git(repo, "checkout", "-q", "--orphan", "unrelated")
    (repo / "x.txt").write_text("x\n")
    git(repo, "add", "x.txt")
    git(repo, "commit", "-q", "-m", "orphan")
    for check in ("immutable-migrations", "squawk"):
        result = run(repo, check)
        assert result.returncode == 1
        assert "fetch-depth: 0" in result.stdout


def test_lookalike_marker_does_not_approve(repo: Path):
    (repo / "migrations" / "0001.sql").write_text("x\n")
    commit(repo)
    body = "not alpha: migration edit approved\n"
    assert run(repo, "immutable-migrations", body=body).returncode == 1


def test_unusual_filename_modified_is_caught(repo: Path):
    name = "migrations/0002 caf\u00e9.sql"
    (repo / name).write_text("a\n")
    commit(repo)
    git(repo, "checkout", "-q", "-b", "next")
    git(repo, "branch", "-f", "main", "feature")
    (repo / name).write_text("b\n")
    commit(repo)
    result = run(repo, "immutable-migrations")
    assert result.returncode == 1
    assert name in result.stdout


def test_unusual_filename_added_reaches_squawk(
    repo: Path, tmp_path: Path, fake_squawk: tuple[Path, Path]
):
    bindir, _ = fake_squawk
    name = "migrations/0002 caf\u00e9.sql"
    argv_log = tmp_path / "argv.log"
    exe = bindir / "squawk"
    exe.write_text(
        f'#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a" >> "{argv_log}"; done\n'
    )
    (repo / name).write_text("select 1;\n")
    commit(repo)
    assert run(repo, "squawk", path=str(bindir)).returncode == 0
    assert argv_log.read_text().splitlines() == [name]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_glob_matcher_matches_the_hooks():
    root = SCRIPT.parents[2]
    ours = _load(SCRIPT, "diff_checks_under_test")
    hooks = _load(root / "project-files" / "hooks" / "_common.py", "common_under_test")
    globs = [
        ["**/migrations/**"],
        ["api/migrations/*.sql"],
        ["migrations/**"],
        ["**"],
        ["a/**/c.sql"],
        ["*.sql", "docs/**"],
    ]
    paths = [
        "migrations/0001.sql",
        "migrations",
        "api/migrations/0001.sql",
        "api/migrations/sub/0002.sql",
        "api/migrations/0001.txt",
        "other/migrations/x/y.sql",
        "a/c.sql",
        "a/b/c.sql",
        "a/b/d/c.sql",
        "x.sql",
        "docs/a/b.md",
        "",
    ]
    for g in globs:
        for p in paths:
            assert ours.matches(p, g) == hooks.matches(p, g), (g, p)
