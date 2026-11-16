import json
import re
import subprocess
import sys
import tempfile
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import stop_checks
from test_repo_checks import REGISTRY, scenario

from alpha.defaults import (
    CONDITIONS,
    DefaultsError,
    Source,
    list_gap,
    load_defaults,
    load_survey,
    locate_source,
    set_default,
)
from alpha.principles import build_principles
from alpha.repo_checks import CI_STEPS, repo_checks

ROOT = Path(__file__).resolve().parents[2]
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
    assert len(ids) == 37
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
        "smallest-change": (
            "standard library",
            "No new dependency for a few lines",
            "Never cut validation at trust boundaries",
        ),
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
    assert "write it into the docs" in statement
    assert "can't be undone" in statement
    weaken = principle(d, "never-weaken-checks")["statement"]
    assert "raise it with the user" not in weaken
    assert "names the path, the rule and why" in weaken


def hook_checks() -> set[tuple[str, str]]:
    hooks = ROOT / "project-files" / "hooks"

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


def test_R12_1_a_user_default_wins(tmp_path: Path):
    src = make_source(tmp_path / "src")
    assert src.user is not None
    src.user.mkdir()
    (src.user / "overrides.toml").write_text(HEADER + "[testing]\ndiff_coverage = 90\n")
    d = load_defaults(src)
    assert d["testing"]["diff_coverage"] == 90
    assert d["testing"]["exhaustive"] is False
    assert load_defaults(Source(src.path, True))["testing"]["diff_coverage"] == 80


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


def test_a_gate_on_a_setup_area_is_rejected_where_the_catalog_is_read(
    tmp_path: Path,
):
    src = make_source(tmp_path / "src")
    p = src.path / "defaults/defaults.toml"
    p.write_text(p.read_text().replace('settled_by = "ui"', 'settled_by = "git"', 1))
    with pytest.raises(DefaultsError, match=r'settled_by "git".*product area'):
        load_defaults(src)


def user_files(src: Source) -> tuple[Path, Path]:
    assert src.user is not None
    return src.user / "overrides.toml", src.user / "CHANGELOG.md"


def test_set_default_writes_your_defaults_and_their_log(tmp_path: Path):
    src = make_source(tmp_path / "src")
    kit = (src.path / "defaults/defaults.toml").read_text()
    saved = set_default(
        src, "testing.diff_coverage", "90", "demo", "small CLIs", date(2026, 10, 19)
    )
    overrides, log = user_files(src)
    assert saved == overrides
    assert overrides.read_text().startswith(HEADER)
    assert tomllib.loads(overrides.read_text())["testing"]["diff_coverage"] == 90
    assert log.read_text() == (
        '# Your alpha defaults\n\nEntries are appended by "alpha defaults set".\n'
        "\n- 2026-10-19 · testing.diff_coverage = 90 · from demo · small CLIs\n"
    )
    assert (src.path / "defaults/defaults.toml").read_text() == kit
    assert load_defaults(src)["testing"]["diff_coverage"] == 90


def test_set_default_keeps_the_changelog_a_valid_list(tmp_path: Path):
    src = make_source(tmp_path / "src")
    day = date(2026, 10, 19)
    set_default(src, "testing.diff_coverage", "90", "demo", "r1", day)
    set_default(src, "testing.exhaustive", "true", "demo", "r2", day)
    assert (
        user_files(src)[1]
        .read_text()
        .endswith(
            "\n\n- 2026-10-19 · testing.diff_coverage = 90 · from demo · r1\n"
            "- 2026-10-19 · testing.exhaustive = true · from demo · r2\n"
        )
    )


def test_set_default_on_a_whitespace_only_changelog(tmp_path: Path):
    src = make_source(tmp_path / "src")
    log = user_files(src)[1]
    log.parent.mkdir()
    log.write_text("  \n\n")
    set_default(src, "testing.diff_coverage", "90", "demo", "r1", date(2026, 10, 19))
    assert log.read_text().endswith(
        "\n- 2026-10-19 · testing.diff_coverage = 90 · from demo · r1\n"
    )


@pytest.mark.parametrize(
    ("existing", "gap"), [("", ""), ("\n\n", ""), ("  ", "\n"), (" \n\t\n", "")]
)
def test_list_gap_without_text_adds_no_blank_line(existing: str, gap: str):
    assert list_gap(existing) == gap


@pytest.mark.slow
def test_changelog_with_entries_passes_rumdl(tmp_path: Path):
    src = make_source(tmp_path / "src")
    day = date(2026, 10, 19)
    set_default(src, "testing.diff_coverage", "90", "demo", "r1", day)
    set_default(src, "testing.exhaustive", "true", "demo", "r2", day)
    pin = REGISTRY.tool("rumdl").pin
    assert pin is not None
    run = subprocess.run(
        ["mise", "exec", f"{pin.mise}@{pin.version}", "--"]
        + ["rumdl", "check", "--no-config", str(user_files(src)[1])],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr


def test_set_default_merges_with_existing_overrides_and_parses_values(tmp_path: Path):
    src = make_source(tmp_path / "src")
    day = date(2026, 10, 19)
    set_default(src, "testing.diff_coverage", "90", "demo", "r", day)
    set_default(src, "testing.exhaustive", "true", "demo", "r", day)
    set_default(src, "protected.paths", '["a", "b"]', "demo", "r", day)
    got = tomllib.loads(user_files(src)[0].read_text())
    assert got["testing"] == {"diff_coverage": 90, "exhaustive": True}
    assert got["protected"]["paths"] == ["a", "b"]


def test_set_default_restores_files_when_a_write_fails(tmp_path: Path):
    src = make_source(tmp_path / "src")
    set_default(src, "testing.diff_coverage", "90", "demo", "r", date(2026, 10, 19))
    overrides, log = user_files(src)
    before = [overrides.read_text(), log.read_text()]
    log.unlink()
    log.mkdir()
    with pytest.raises(DefaultsError, match="retry"):
        set_default(src, "testing.diff_coverage", "95", "demo", "r", date.today())
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
    """A default set with alpha defaults set shows on top of the kit's."""
    env = cli_env(tmp_path)
    shown = run_cli("defaults", "show", "--json", env=env)
    assert shown.returncode == 0, shown.stderr
    data = json.loads(shown.stdout)
    assert data["source"] == {
        "path": str(ROOT),
        "checkout": False,
        "user_defaults": None,
    }
    assert data["defaults"]["testing"]["diff_coverage"] == 80
    done = run_cli(
        *("defaults", "set", "--key", "testing.diff_coverage", "--value", "70"),
        *("--project", "demo", "--reason", "why"),
        env=env,
    )
    assert done.returncode == 0, done.stderr
    mine = tmp_path / "config/overrides.toml"
    assert done.stdout == (
        f"saved: testing.diff_coverage = 70 in {mine}; new projects use it\n"
    )
    text = run_cli("defaults", "show", env=env)
    assert text.stdout.startswith(
        f"kit defaults from the alpha plugin at {ROOT}\n"
        f"with your defaults from {mine}\n"
    )
    assert "diff_coverage = 70" in text.stdout
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
        (
            "testing.diff_coverage",
            "lots",
            "testing.diff_coverage must be a whole number",
        ),
        (
            "testing.diff_coverage",
            "true",
            "testing.diff_coverage must be a whole number",
        ),
        ("git.convention", "3", "git.convention must be text"),
        ("review.risk_paths", "docs/**", "review.risk_paths must be a list of text"),
        ("review.risk_paths", "[1, 2]", "review.risk_paths must be a list of text"),
    ],
)
def test_set_default_rejects_unknown_keys_and_wrong_types(
    tmp_path: Path, key: str, value: str, expected: str
):
    src = make_source(tmp_path / "src")
    with pytest.raises(DefaultsError) as e:
        set_default(src, key, value, "demo", "r", date(2026, 10, 19))
    assert str(e.value).startswith(expected)
    assert "testing.diff_coverage" in str(e.value) or "--value" in str(e.value)
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


SURVEY_KEYS = (
    "ci",
    "docs",
    "migrations",
    "task_runners",
    "hook_managers",
    "license",
    "env_examples",
)


def test_survey_globs_load(tmp_path: Path):
    globs = load_survey(Source(ROOT, True))
    for key in SURVEY_KEYS:
        assert globs[key], key
    # A checkout without the file falls back to the plugin's.
    assert load_survey(make_source(tmp_path / "alpha")) == globs


def test_bad_survey_globs_are_named(tmp_path: Path):
    source = make_source(tmp_path / "alpha")
    (tmp_path / "alpha/defaults/survey.toml").write_text('ci = "x"\n')
    with pytest.raises(DefaultsError, match="ci must be a list of globs"):
        load_survey(source)
