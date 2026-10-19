import json
import subprocess
import sys
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
    assert len(ids) == 28
    assert d["review"]["risk_paths"][:5] == [
        "**/migrations/**",
        "**/*.proto",
        "**/openapi*.yaml",
        "**/openapi*.yml",
        "**/openapi*.json",
    ]


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


def test_cli_set_not_live_exits_3(tmp_path: Path):
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    done = run_cli(
        *("defaults", "set", "--key", "a.b", "--value", "1"),
        *("--project", "p", "--reason", "r"),
        env=env,
    )
    assert done.returncode == 3
    assert "decision log" in done.stderr
