import subprocess
import tomllib
from datetime import timedelta
from pathlib import Path

import pytest
from helpers import PLUGIN_ROOT, run_cli

from alpha.defaults import Source
from alpha.registry import Registry, RegistryError, load_registry

GENERATED = (
    "jactionlint",
    "betterleaks",
    "osv-scanner",
    "typos",
    "rumdl",
    "lychee",
    "agnix",
    "squawk",
    "diff-cover",
)


def kit() -> Registry:
    return load_registry(Source(PLUGIN_ROOT, True, ""))


def test_registry_loads():
    pin = kit().tool("typos").pin
    assert pin is not None
    assert pin.fails_with != 0


@pytest.mark.parametrize("tool_id", GENERATED)
def test_generated_tools_are_pinned(tool_id: str):
    pin = kit().tool(tool_id).pin
    assert pin is not None
    assert pin.mise and pin.version and pin.command


def test_for_stack_lists_the_stack_and_cross_cutting_tools():
    ids = {t.id for t in kit().for_stack("python")}
    assert {"ruff", "pyright", "typos"} <= ids
    assert "biome" not in ids


def bad_registry(tmp_path: Path, field: str, value: str) -> Source:
    fields = {
        "name": '"Demo"',
        "repo": '"a/b"',
        "category": '"Python"',
        "stacks": '["python"]',
        "rationale": '"r"',
        "limitations": '"l"',
        "last_reviewed": "2026-11-09",
        field: value,
    }
    folder = tmp_path / "registry"
    folder.mkdir()
    body = "".join(f"{k} = {v}\n" for k, v in fields.items())
    (folder / "tools.toml").write_text(f"[tools.demo]\n{body}")
    (folder / "actions.toml").write_text("")
    return Source(tmp_path, True, "")


def test_bad_field_names_it(tmp_path: Path):
    source = bad_registry(tmp_path, "last_reviewed", '"soon"')
    with pytest.raises(RegistryError, match=r"tools\.demo\.last_reviewed"):
        load_registry(source)


def test_incomplete_pin_names_the_field(tmp_path: Path):
    source = bad_registry(tmp_path, "pin", '{ mise = "demo", version = "1.0.0" }')
    with pytest.raises(RegistryError, match=r"tools\.demo\.pin\.command"):
        load_registry(source)


def test_a_live_checkout_without_a_registry_falls_back_to_the_bundled_one(
    tmp_path: Path,
):
    reg = load_registry(Source(tmp_path, True, ""))
    assert reg.tool("typos").pin is not None


def test_stale():
    reg = kit()
    tool = reg.tool("ruff")
    assert tool in reg.stale(tool.last_reviewed + timedelta(days=181))
    assert tool not in reg.stale(tool.last_reviewed + timedelta(days=180))


def test_unknown_tool_and_action_say_how_to_list():
    with pytest.raises(RegistryError, match="alpha registry list"):
        kit().tool("nope")
    with pytest.raises(RegistryError, match="actions.toml"):
        kit().action("nope/nope")


def test_actions_are_full_shas():
    for repo in ("actions/checkout", "jdx/mise-action", "astral-sh/setup-uv"):
        action = kit().action(repo)
        assert len(action.sha) == 40 and action.version.startswith("v")


def test_cli_show():
    done = run_cli("registry", "show", "ruff")
    assert done.returncode == 0
    assert kit().tool("ruff").rationale in done.stdout
    missing = run_cli("registry", "show", "nope")
    assert missing.returncode == 1
    assert "alpha registry list" in missing.stderr


def test_cli_list_and_stale():
    done = run_cli("registry", "list", "--stack", "python")
    assert done.returncode == 0
    assert "ruff" in done.stdout.split()
    assert "biome" not in done.stdout.split()
    assert run_cli("registry", "stale").returncode == 0


@pytest.mark.slow
def test_action_shas_match_tags():
    entries = tomllib.loads((PLUGIN_ROOT / "registry/actions.toml").read_text())
    for repo, entry in entries["actions"].items():
        tag = f"refs/tags/{entry['version']}"
        out = subprocess.run(
            ["git", "ls-remote", f"https://github.com/{repo}", tag, f"{tag}^{{}}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        # An annotated tag lists its own object first and the commit as ^{}.
        shas = {line.split()[1]: line.split()[0] for line in out.splitlines()}
        assert shas.get(f"{tag}^{{}}", shas.get(tag)) == entry["sha"], repo
