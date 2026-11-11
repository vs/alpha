import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from alpha.defaults import (
    CONDITIONS,
    DefaultsError,
    Source,
    _list_gap,
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


def make_source(path: Path) -> Source:
    (path / "defaults").mkdir(parents=True)
    defaults = ROOT / "defaults/defaults.toml"
    (path / "defaults/defaults.toml").write_text(defaults.read_text())
    return Source(path, True, path.parent / "config")


def test_the_installed_plugin_is_the_source(tmp_path: Path):
    make_source(tmp_path / "home/workspace/alpha")
    s = locate_source(tmp_path / "plugin", {}, tmp_path / "home")
    assert s == Source(tmp_path / "plugin", False, tmp_path / "home/.config/alpha")


def test_alpha_source_names_a_checkout(tmp_path: Path):
    src = make_source(tmp_path / "mine")
    env = {"ALPHA_SOURCE": str(src.path), "ALPHA_CONFIG_DIR": str(tmp_path / "c")}
    s = locate_source(tmp_path / "plugin", env, tmp_path)
    assert s == Source(src.path, True, tmp_path / "c")


def test_a_wrong_alpha_source_is_explained(tmp_path: Path):
    with pytest.raises(DefaultsError) as e:
        locate_source(tmp_path / "plugin", {"ALPHA_SOURCE": str(tmp_path)}, tmp_path)
    assert str(e.value).startswith(f"ALPHA_SOURCE is {tmp_path}, which has no ")
    assert "unset it to use the installed plugin" in str(e.value)


def test_catalog_has_all_core_principles():
    d = load_defaults(Source(ROOT, True))
    ids = {p["id"] for p in d["principles"]}
    assert {
        "fail-helpfully",
        "never-weaken-checks",
        "clean-history",
        "definition-of-done",
    } <= ids
    assert len(ids) == 35
    assert d["review"]["risk_paths"][:5] == [
        "**/migrations/**",
        "**/*.proto",
        "**/openapi*.yaml",
        "**/openapi*.yml",
        "**/openapi*.json",
    ]


def principle(d: dict[str, Any], pid: str) -> dict[str, Any]:
    return next(p for p in d["principles"] if p["id"] == pid)


def test_comments_keep_only_what_the_code_cannot_say():
    d = load_defaults(Source(ROOT, True))
    statement = principle(d, "code-over-comments")["statement"]
    for kept in ("license", "dependency", "public API", "issue"):
        assert kept in statement
    assert "renaming" in statement
    assert "comments-say-why" not in {p["id"] for p in d["principles"]}


def test_subtract_first_replaces_internal_apis_in_one_change():
    d = load_defaults(Source(ROOT, True))
    statement = principle(d, "subtract-first")["statement"]
    assert "dead" in statement
    assert "compatibility layer" in statement
    assert principle(d, "subtract-first")["applies"] == ["always"]


def test_ponytail_code_writing_principles_are_core():
    d = load_defaults(Source(ROOT, True))
    texts = {
        "smallest-change": ("standard library", "No new dependency for a few lines"),
        "scope-first": ("callers, tests, fixtures, config, exports",),
        "fix-at-the-root": ("every caller", "keeps its error handling and validation"),
        "lean-structure": ("split by job, never by line count", "edge cases"),
    }
    for pid, fragments in texts.items():
        p = principle(d, pid)
        assert p["core"] is True and p["applies"] == ["always"], pid
        assert all(f in p["statement"] for f in fragments), pid


def test_branching_defaults_to_feature_branches():
    d = load_defaults(Source(ROOT, True))
    assert d["git"]["branching"] == "feature-branches"


def test_reversible_work_does_not_wait_for_the_user():
    d = load_defaults(Source(ROOT, True))
    ids = {p["id"] for p in d["principles"]}
    assert "ask-when-ambiguous" not in ids
    statement = principle(d, "never-block-on-the-human")["statement"]
    assert "record it in the decision log" in statement
    assert "can't be undone" in statement
    weaken = principle(d, "never-weaken-checks")["statement"]
    assert "raise it with the user" not in weaken
    assert "names the path and the rule" in weaken


def hook_checks() -> set[tuple[str, str]]:
    hooks = ROOT / "project-files" / "hooks"
    sys.path.insert(0, str(hooks))
    import stop_checks

    found = {(p, "hook:stop_checks") for p in stop_checks.COMMAND_PRINCIPLES.values()}
    call = re.compile(r'principle_applies\(\s*\w+,\s*"([a-z-]+)"')
    for script in hooks.glob("*.py"):
        found |= {(p, f"hook:{script.stem}") for p in call.findall(script.read_text())}
    return found


def test_checked_by_names_the_hooks_that_check_each_principle():
    d = load_defaults(Source(ROOT, True))
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
            load_defaults(Source(ROOT, True)), a, "0.1.0", registry=REGISTRY
        )
        return {c.id for c in repo_checks(a, principles, REGISTRY)}


def test_checked_by_prefixes_are_known():
    """`reviewer`, `hook:<script>` (checked above) or `ci:<check>`."""
    d = load_defaults(Source(ROOT, True))
    ci_checks = catalog_ids() | set(CI_STEPS)
    for p in d["principles"]:
        for who in p["checked_by"]:
            kind, _, name = who.partition(":")
            assert kind in ("reviewer", "hook", "ci"), (p["id"], who)
            if kind == "ci":
                assert name in ci_checks, (p["id"], who)
            if kind == "reviewer":
                assert not name


def test_your_defaults_layer_over_the_kit(tmp_path: Path):
    src = make_source(tmp_path / "src")
    assert src.user is not None
    src.user.mkdir()
    (src.user / "overrides.toml").write_text(HEADER + "[review]\nmax_lines = 400\n")
    d = load_defaults(src)
    assert d["review"]["max_lines"] == 400
    assert d["review"]["max_files"] == 5
    assert load_defaults(Source(src.path, True))["review"]["max_lines"] == 200


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


def user_files(src: Source) -> tuple[Path, Path]:
    assert src.user is not None
    return src.user / "overrides.toml", src.user / "CHANGELOG.md"


def test_set_default_writes_your_defaults_and_their_log(tmp_path: Path):
    src = make_source(tmp_path / "src")
    kit = (src.path / "defaults/defaults.toml").read_text()
    saved = set_default(
        src, "review.max_lines", "400", "demo", "small CLIs", date(2026, 10, 19)
    )
    overrides, log = user_files(src)
    assert saved == overrides
    assert overrides.read_text().startswith(HEADER)
    assert tomllib.loads(overrides.read_text())["review"]["max_lines"] == 400
    assert log.read_text() == (
        '# Your alpha defaults\n\nEntries are appended by "alpha defaults set".\n'
        "\n- 2026-10-19 · review.max_lines = 400 · from demo · small CLIs\n"
    )
    assert (src.path / "defaults/defaults.toml").read_text() == kit
    assert load_defaults(src)["review"]["max_lines"] == 400


def test_set_default_keeps_the_changelog_a_valid_list(tmp_path: Path):
    src = make_source(tmp_path / "src")
    day = date(2026, 10, 19)
    set_default(src, "review.max_lines", "400", "demo", "r1", day)
    set_default(src, "review.mode", "every-task", "demo", "r2", day)
    assert (
        user_files(src)[1]
        .read_text()
        .endswith(
            "\n\n- 2026-10-19 · review.max_lines = 400 · from demo · r1\n"
            "- 2026-10-19 · review.mode = every-task · from demo · r2\n"
        )
    )


def test_set_default_on_a_whitespace_only_changelog(tmp_path: Path):
    src = make_source(tmp_path / "src")
    log = user_files(src)[1]
    log.parent.mkdir()
    log.write_text("  \n\n")
    set_default(src, "review.max_lines", "400", "demo", "r1", date(2026, 10, 19))
    assert log.read_text().endswith(
        "\n- 2026-10-19 · review.max_lines = 400 · from demo · r1\n"
    )


@pytest.mark.parametrize(
    ("existing", "gap"), [("", ""), ("\n\n", ""), ("  ", "\n"), (" \n\t\n", "")]
)
def test_list_gap_without_text_adds_no_blank_line(existing: str, gap: str):
    assert _list_gap(existing) == gap


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("rumdl") is None, reason="rumdl is not installed")
def test_changelog_with_entries_passes_rumdl(tmp_path: Path):
    src = make_source(tmp_path / "src")
    day = date(2026, 10, 19)
    set_default(src, "review.max_lines", "400", "demo", "r1", day)
    set_default(src, "review.mode", "every-task", "demo", "r2", day)
    run = subprocess.run(
        ["rumdl", "check", "--no-config", str(user_files(src)[1])],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr


def test_set_default_merges_with_existing_overrides_and_parses_values(tmp_path: Path):
    src = make_source(tmp_path / "src")
    day = date(2026, 10, 19)
    set_default(src, "review.max_lines", "400", "demo", "r", day)
    set_default(src, "review.mode", "every-task", "demo", "r", day)
    set_default(src, "protected.paths", '["a", "b"]', "demo", "r", day)
    got = tomllib.loads(user_files(src)[0].read_text())
    assert got["review"] == {"max_lines": 400, "mode": "every-task"}
    assert got["protected"]["paths"] == ["a", "b"]


def test_set_default_restores_files_when_a_write_fails(tmp_path: Path):
    src = make_source(tmp_path / "src")
    set_default(src, "review.max_lines", "400", "demo", "r", date(2026, 10, 19))
    overrides, log = user_files(src)
    before = [overrides.read_text(), log.read_text()]
    log.unlink()
    log.mkdir()
    with pytest.raises(DefaultsError, match="retry"):
        set_default(src, "review.max_lines", "500", "demo", "r", date.today())
    assert overrides.read_text() == before[0]


def test_set_default_needs_a_folder_for_your_defaults(tmp_path: Path):
    with pytest.raises(DefaultsError, match="ALPHA_CONFIG_DIR"):
        set_default(Source(tmp_path, False), "a.b", "1", "p", "r", date.today())


def run_cli(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SHIM), *args], capture_output=True, text=True, env=env
    )


def cli_env(tmp_path: Path, src: Source | None = None) -> dict[str, str]:
    env = {
        "HOME": str(tmp_path),
        "ALPHA_CONFIG_DIR": str(tmp_path / "config"),
        "PATH": "/usr/bin:/bin",
    }
    if src is not None:
        env["ALPHA_SOURCE"] = str(src.path)
    return env


def test_cli_show_json_and_set(tmp_path: Path):
    env = cli_env(tmp_path)
    shown = run_cli("defaults", "show", "--json", env=env)
    assert shown.returncode == 0, shown.stderr
    data = json.loads(shown.stdout)
    assert data["source"] == {
        "path": str(ROOT),
        "checkout": False,
        "user_defaults": None,
    }
    assert data["defaults"]["review"]["max_lines"] == 200
    done = run_cli(
        *("defaults", "set", "--key", "review.max_lines", "--value", "300"),
        *("--project", "demo", "--reason", "why"),
        env=env,
    )
    assert done.returncode == 0, done.stderr
    mine = tmp_path / "config/overrides.toml"
    assert done.stdout == (
        f"saved: review.max_lines = 300 in {mine}; new projects use it\n"
    )
    text = run_cli("defaults", "show", env=env)
    assert text.stdout.startswith(
        f"kit defaults from the alpha plugin at {ROOT}\n"
        f"with your defaults from {mine}\n"
    )
    assert "max_lines = 300" in text.stdout
    data = json.loads(run_cli("defaults", "show", "--json", env=env).stdout)
    assert data["source"]["user_defaults"] == str(mine)


def test_cli_names_an_alpha_source_checkout(tmp_path: Path):
    src = make_source(tmp_path / "src")
    text = run_cli("defaults", "show", env=cli_env(tmp_path, src))
    assert text.stdout.startswith(
        f"kit defaults from the alpha checkout (ALPHA_SOURCE) at {src.path}\n"
    )


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
    src = make_source(tmp_path / "src")
    with pytest.raises(DefaultsError) as e:
        set_default(src, key, value, "demo", "r", date(2026, 10, 19))
    assert str(e.value).startswith(expected)
    assert "review.max_lines" in str(e.value) or "--value" in str(e.value)
    assert not any(f.exists() for f in user_files(src))


def test_cli_set_rejects_an_unknown_key_with_exit_3(tmp_path: Path):
    done = run_cli(
        *("defaults", "set", "--key", "review.nope", "--value", "1"),
        *("--project", "p", "--reason", "r"),
        env=cli_env(tmp_path),
    )
    assert done.returncode == 3
    assert "Traceback" not in done.stderr
    assert '"review.nope" is not a kit default' in done.stderr


def test_malformed_kit_defaults_are_explained(tmp_path: Path):
    src = make_source(tmp_path / "src")
    kit = src.path / "defaults/defaults.toml"
    kit.write_text("review = [oops\n")
    with pytest.raises(DefaultsError) as e:
        load_defaults(src)
    assert str(e.value).startswith(f"{kit} is not valid TOML")
    assert f"git -C {src.path} checkout defaults/defaults.toml" in str(e.value)
    with pytest.raises(DefaultsError, match="reinstall the alpha plugin"):
        load_defaults(Source(src.path, False))
    shown = run_cli("defaults", "show", env=cli_env(tmp_path, src))
    assert shown.returncode == 3
    assert "Traceback" not in shown.stderr
    assert "is not valid TOML" in shown.stderr


def test_malformed_user_defaults_are_explained(tmp_path: Path):
    src = make_source(tmp_path / "src")
    mine = user_files(src)[0]
    mine.parent.mkdir()
    mine.write_text("review = [oops\n")
    with pytest.raises(DefaultsError) as e:
        load_defaults(src)
    assert str(e.value).startswith(f"{mine} is not valid TOML")
    assert "delete it to go back to the kit's defaults" in str(e.value)
