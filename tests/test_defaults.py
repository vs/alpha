import json
import re
import subprocess
import sys
import tempfile
import tomllib
from datetime import date
from pathlib import Path

import pytest

from alpha.defaults import (
    CONDITIONS,
    DefaultsError,
    Source,
    load_defaults,
    locate_source,
    set_default,
)
from alpha.principles import build_principles
from alpha.repo_checks import CI_STEPS, repo_checks

ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "bin" / "alpha"
HEADER = '# Managed by "alpha defaults set". Do not edit by hand.\n'


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def make_source(path: Path, *, repo: bool = False) -> Source:
    (path / "defaults").mkdir(parents=True)
    for name in ("defaults.toml", "overrides.toml", "CHANGELOG.md"):
        (path / "defaults" / name).write_text((ROOT / "defaults" / name).read_text())
    if repo:
        git(path, "init", "-q")
        git(path, "config", "user.name", "Test")
        git(path, "config", "user.email", "test@example.com")
        git(path, "add", "-A")
        git(path, "commit", "-q", "-m", "chore: Seed")
    return Source(path, True, "")


def test_env_source_wins(tmp_path: Path):
    src = make_source(tmp_path / "mine")
    s = locate_source(tmp_path / "plugin", {"ALPHA_SOURCE": str(src.path)}, tmp_path)
    assert s.live is True and s.path == src.path


def test_config_file_source(tmp_path: Path):
    src = make_source(tmp_path / "elsewhere")
    cfg = tmp_path / "home/.config/alpha/config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(f'source = "{src.path}"\n')
    s = locate_source(tmp_path / "plugin", {}, tmp_path / "home")
    assert s.live is True and s.path == src.path


def test_default_workspace_source(tmp_path: Path):
    src = make_source(tmp_path / "home/workspace/alpha")
    s = locate_source(tmp_path / "plugin", {}, tmp_path / "home")
    assert s.live is True and s.path == src.path


def test_fallback_is_bundled_and_explains(tmp_path: Path):
    s = locate_source(tmp_path / "plugin", {}, tmp_path / "home")
    assert s.live is False and s.path == tmp_path / "plugin"
    assert "ALPHA_SOURCE" in s.reason
    assert str(tmp_path / "home/workspace/alpha") in s.reason


def test_catalog_has_all_core_principles():
    d = load_defaults(Source(ROOT, True, ""))
    ids = {p["id"] for p in d["principles"]}
    assert {
        "fail-helpfully",
        "never-weaken-checks",
        "clean-history",
        "definition-of-done",
    } <= ids
    assert len(ids) == 30
    assert d["review"]["risk_paths"][:5] == [
        "**/migrations/**",
        "**/*.proto",
        "**/openapi*.yaml",
        "**/openapi*.yml",
        "**/openapi*.json",
    ]


def hook_checks() -> set[tuple[str, str]]:
    """(principle id, hook:<script>) for every principle a hook gates on."""
    hooks = ROOT / "project-files" / "hooks"
    sys.path.insert(0, str(hooks))
    import stop_checks

    found = {(p, "hook:stop_checks") for p in stop_checks.COMMAND_PRINCIPLES.values()}
    call = re.compile(r'principle_applies\(\s*\w+,\s*"([a-z-]+)"')
    for script in hooks.glob("*.py"):
        found |= {(p, f"hook:{script.stem}") for p in call.findall(script.read_text())}
    return found


def test_checked_by_names_the_hooks_that_check_each_principle():
    d = load_defaults(Source(ROOT, True, ""))
    listed = {
        (p["id"], who)
        for p in d["principles"]
        for who in p["checked_by"]
        if who.startswith("hook:")
    }
    assert listed == hook_checks()
    unreviewed = [p["id"] for p in d["principles"] if "reviewer" not in p["checked_by"]]
    assert unreviewed == []


def catalog_ids() -> set[str]:
    """Every repository check id, from a project with every conditional on."""
    from test_repo_checks import REGISTRY, scenario

    with tempfile.TemporaryDirectory() as tmp:
        a, _ = scenario(Path(tmp), "web-ts-plus-python-api")
        principles = build_principles(
            load_defaults(Source(ROOT, True, "")), a, "0.1.0", registry=REGISTRY
        )
        return {c.id for c in repo_checks(a, principles, REGISTRY)}


def test_checked_by_prefixes_are_known():
    """`reviewer`, `hook:<script>` (checked above) or `ci:<check>`."""
    d = load_defaults(Source(ROOT, True, ""))
    ci_checks = catalog_ids() | set(CI_STEPS)
    for p in d["principles"]:
        for who in p["checked_by"]:
            kind, _, name = who.partition(":")
            assert kind in ("reviewer", "hook", "ci"), (p["id"], who)
            if kind == "ci":
                assert name in ci_checks, (p["id"], who)
            if kind == "reviewer":
                assert not name


def test_overrides_layer_wins(tmp_path: Path):
    src = make_source(tmp_path / "src")
    (src.path / "defaults/overrides.toml").write_text(
        HEADER + "[review]\nmax_lines = 400\n"
    )
    d = load_defaults(src)
    assert d["review"]["max_lines"] == 400
    assert d["review"]["max_files"] == 5


def test_unknown_condition_is_rejected_with_hint(tmp_path: Path):
    src = make_source(tmp_path / "src")
    p = src.path / "defaults/defaults.toml"
    p.write_text(
        p.read_text().replace('applies = ["has_ui"]', 'applies = ["sometimes"]', 1)
    )
    with pytest.raises(DefaultsError) as e:
        load_defaults(src)
    assert "sometimes" in str(e.value)
    assert all(c in str(e.value) for c in CONDITIONS)


def test_set_default_writes_logs_and_commits(tmp_path: Path):
    src = make_source(tmp_path / "src", repo=True)
    h = set_default(
        src,
        "review.max_lines",
        "400",
        "demo",
        "small CLIs",
        ["Co-Authored-By: X <x@y>"],
        date(2026, 10, 19),
    )
    overrides = (src.path / "defaults/overrides.toml").read_text()
    assert overrides.startswith(HEADER)
    assert tomllib.loads(overrides)["review"]["max_lines"] == 400
    log = (src.path / "defaults/CHANGELOG.md").read_text()
    assert "2026-10-19 · review.max_lines = 400 · from demo · small CLIs" in log
    assert git(src.path, "log", "-1", "--format=%s") == "chore(defaults): Set max_lines"
    assert "Co-Authored-By: X <x@y>" in git(src.path, "log", "-1", "--format=%B")
    assert git(src.path, "rev-parse", "HEAD").startswith(h) and len(h) >= 7


def test_set_default_merges_with_existing_overrides_and_parses_values(tmp_path: Path):
    src = make_source(tmp_path / "src", repo=True)
    day = date(2026, 10, 19)
    set_default(src, "review.max_lines", "400", "demo", "r", [], day)
    set_default(src, "review.mode", "every-task", "demo", "r", [], day)
    set_default(src, "protected.paths", '["a", "b"]', "demo", "r", [], day)
    got = tomllib.loads((src.path / "defaults/overrides.toml").read_text())
    assert got["review"] == {"max_lines": 400, "mode": "every-task"}
    assert got["protected"]["paths"] == ["a", "b"]


def reject_commits(repo: Path) -> None:
    """Make every commit in repo fail through a pre-commit hook."""
    hooks = repo.parent / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'rejected by test hook' >&2\nexit 1\n")
    hook.chmod(0o755)
    git(repo, "config", "core.hooksPath", str(hooks))


def test_set_default_commits_only_its_own_files(tmp_path: Path):
    src = make_source(tmp_path / "src", repo=True)
    (src.path / "unrelated.txt").write_text("staged work in progress\n")
    git(src.path, "add", "unrelated.txt")
    set_default(src, "review.max_lines", "400", "demo", "r", [], date(2026, 10, 19))
    committed = git(src.path, "show", "--name-only", "--format=", "HEAD").split()
    assert sorted(committed) == ["defaults/CHANGELOG.md", "defaults/overrides.toml"]
    assert git(src.path, "status", "--porcelain") == "A  unrelated.txt"


@pytest.mark.parametrize("repo", [True, False], ids=["commit-fails", "no-repo"])
def test_set_default_restores_files_when_git_fails(tmp_path: Path, repo: bool):
    src = make_source(tmp_path / "src", repo=repo)
    if repo:
        reject_commits(src.path)
    files = [src.path / "defaults/overrides.toml", src.path / "defaults/CHANGELOG.md"]
    before = [f.read_text() for f in files]
    with pytest.raises(DefaultsError, match="retry"):
        set_default(src, "review.max_lines", "400", "demo", "r", [], date.today())
    assert [f.read_text() for f in files] == before
    if repo:
        assert git(src.path, "status", "--porcelain") == ""


def test_set_default_removes_a_new_overrides_file_when_git_fails(tmp_path: Path):
    src = make_source(tmp_path / "src", repo=True)
    git(src.path, "rm", "-q", "defaults/overrides.toml")
    git(src.path, "commit", "-q", "-m", "chore: Drop overrides")
    reject_commits(src.path)
    with pytest.raises(DefaultsError):
        set_default(src, "review.max_lines", "400", "demo", "r", [], date.today())
    assert not (src.path / "defaults/overrides.toml").exists()
    assert git(src.path, "status", "--porcelain") == ""


def test_set_default_refuses_when_not_live(tmp_path: Path):
    with pytest.raises(DefaultsError, match="decision log"):
        set_default(
            Source(tmp_path, False, "bundled"), "a.b", "1", "p", "r", [], date.today()
        )


def run_cli(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SHIM), *args], capture_output=True, text=True, env=env
    )


def test_cli_show_json_and_set(tmp_path: Path):
    src = make_source(tmp_path / "src", repo=True)
    env = {
        "ALPHA_SOURCE": str(src.path),
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
    }
    shown = run_cli("defaults", "show", "--json", env=env)
    assert shown.returncode == 0, shown.stderr
    data = json.loads(shown.stdout)
    assert data["source"]["live"] is True
    assert data["defaults"]["review"]["max_lines"] == 200
    text = run_cli("defaults", "show", env=env)
    assert text.stdout.startswith(f"live from {src.path}\n")
    done = run_cli(
        *("defaults", "set", "--key", "review.max_lines", "--value", "300"),
        *("--project", "demo", "--reason", "why", "--trailer", "Claude-Session: s"),
        env=env,
    )
    assert done.returncode == 0, done.stderr
    assert git(src.path, "rev-parse", "HEAD").startswith(done.stdout.strip())


def test_cli_set_not_live_exits_4(tmp_path: Path):
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    done = run_cli(
        *("defaults", "set", "--key", "a.b", "--value", "1"),
        *("--project", "p", "--reason", "r"),
        env=env,
    )
    assert done.returncode == 4
    assert "decision log" in done.stderr


def test_cli_set_git_failure_exits_3_and_explains(tmp_path: Path):
    src = make_source(tmp_path / "src", repo=True)
    reject_commits(src.path)
    env = {
        "ALPHA_SOURCE": str(src.path),
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
    }
    done = run_cli(
        *("defaults", "set", "--key", "review.max_lines", "--value", "300"),
        *("--project", "demo", "--reason", "why"),
        env=env,
    )
    assert done.returncode == 3
    assert "git commit failed" in done.stderr
    assert "retry" in done.stderr


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("review.nope", "1", '"review.nope" is not a kit default'),
        ("principles.x", "1", '"principles.x" is not a kit default'),
        ("review", "1", '"review" is a table of settings'),
        ("principles", "[]", '"principles" is a table of settings'),
        ("review.max_lines", "lots", "review.max_lines must be a whole number"),
        ("review.max_lines", "true", "review.max_lines must be a whole number"),
        ("review.mode", "3", "review.mode must be text"),
        ("review.exclude", "docs/**", "review.exclude must be a list of text"),
        ("review.exclude", "[1, 2]", "review.exclude must be a list of text"),
    ],
)
def test_set_default_rejects_unknown_keys_and_wrong_types(
    tmp_path: Path, key: str, value: str, expected: str
):
    src = make_source(tmp_path / "src", repo=True)
    head = git(src.path, "rev-parse", "HEAD")
    files = [src.path / "defaults/overrides.toml", src.path / "defaults/CHANGELOG.md"]
    before = [f.read_text() for f in files]
    with pytest.raises(DefaultsError) as e:
        set_default(src, key, value, "demo", "r", [], date(2026, 10, 19))
    assert str(e.value).startswith(expected)
    assert "review.max_lines" in str(e.value) or "--value" in str(e.value)
    assert [f.read_text() for f in files] == before
    assert git(src.path, "rev-parse", "HEAD") == head
    assert git(src.path, "status", "--porcelain") == ""


def test_cli_set_rejects_an_unknown_key_with_exit_3(tmp_path: Path):
    src = make_source(tmp_path / "src", repo=True)
    env = {
        "ALPHA_SOURCE": str(src.path),
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
    }
    done = run_cli(
        *("defaults", "set", "--key", "review.nope", "--value", "1"),
        *("--project", "p", "--reason", "r"),
        env=env,
    )
    assert done.returncode == 3
    assert "Traceback" not in done.stderr
    assert '"review.nope" is not a kit default' in done.stderr


@pytest.mark.parametrize("name", ["defaults.toml", "overrides.toml"])
def test_malformed_defaults_are_explained(tmp_path: Path, name: str):
    src = make_source(tmp_path / "src", repo=True)
    (src.path / "defaults" / name).write_text("review = [oops\n")
    with pytest.raises(DefaultsError) as e:
        load_defaults(src)
    assert str(e.value).startswith(f"{src.path / 'defaults' / name} is not valid TOML")
    assert f"git -C {src.path} checkout defaults/{name}" in str(e.value)
    env = {
        "ALPHA_SOURCE": str(src.path),
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
    }
    shown = run_cli("defaults", "show", env=env)
    assert shown.returncode == 3
    assert "Traceback" not in shown.stderr
    assert "is not valid TOML" in shown.stderr
