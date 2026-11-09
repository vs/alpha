import json
import re
import tomllib
from pathlib import Path
from typing import Any

from helpers import SCENARIOS, TODAY

from alpha.answers import Answers, load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.generate import render_project
from alpha.recipes import check_commands
from alpha.registry import load_registry
from alpha.render.tooling import render_tooling
from alpha.repo_checks import repo_checks

SOURCE = Source(PLUGIN_ROOT, True, "")
D = load_defaults(SOURCE)
REGISTRY = load_registry(SOURCE)


def answers(tmp_path: Path, name: str) -> Answers:
    data = json.loads((SCENARIOS / f"{name}.json").read_text())
    path = tmp_path / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data))
    return load_answers(path)


def texts(tmp_path: Path, name: str) -> dict[str, str]:
    a = answers(tmp_path, name)
    return render_project(tmp_path, a, D, 2026, TODAY, registry=REGISTRY).texts


def mise(tmp_path: Path, name: str) -> dict[str, Any]:
    return tomllib.loads(texts(tmp_path, name)["mise.toml"])


def test_render_tooling_returns_the_four_files(tmp_path: Path):
    a = answers(tmp_path, "rust-cli")
    rendered = render_project(tmp_path, a, D, 2026, TODAY, registry=REGISTRY)
    checks = repo_checks(a, rendered.principles, REGISTRY)
    components = rendered.principles["components"]
    out = render_tooling(checks, REGISTRY, ["target/"], components=components)
    assert set(out) == {"mise.toml", ".rumdl.toml", "_typos.toml", "lychee.toml"}
    assert set(out) <= set(rendered.texts)
    assert "target/" in tomllib.loads(out["_typos.toml"])["files"]["extend-exclude"]


def test_mise_pins_registry_versions(tmp_path: Path):
    a = answers(tmp_path, "web-ts-plus-python-api")
    rendered = render_project(tmp_path, a, D, 2026, TODAY, registry=REGISTRY)
    checks = repo_checks(a, rendered.principles, REGISTRY)
    data = tomllib.loads(rendered.texts["mise.toml"])
    expected: dict[str, str] = {}
    for check in checks:
        if check.tool:
            pin = REGISTRY.tool(check.tool).pin
            assert pin is not None
            expected[pin.mise] = pin.version
    assert data["tools"] == expected
    assert data["tools"]["typos"] == REGISTRY.tool("typos").pin.version  # pyright: ignore[reportOptionalMemberAccess]
    assert "check:typos" in data["tasks"]["ci"]["depends"]


def test_mise_tasks_install_no_global_tools(tmp_path: Path):
    # Otherwise `mise run` installs every missing tool of the user's global
    # config at each Stop and `mise run ci`.
    data = mise(tmp_path, "rust-cli")
    assert data["settings"] == {"task": {"run_auto_install": False}}


def test_mise_tasks_follow_the_catalog(tmp_path: Path):
    a = answers(tmp_path, "web-ts-plus-python-api")
    rendered = render_project(tmp_path, a, D, 2026, TODAY, registry=REGISTRY)
    checks = repo_checks(a, rendered.principles, REGISTRY)
    tasks = tomllib.loads(rendered.texts["mise.toml"])["tasks"]
    for check in checks:
        assert tasks[f"check:{check.id}"]["run"] == check.command
    assert tasks["ci"]["depends"] == [
        f"check:{c.id}" for c in checks if c.when in ("pr", "both")
    ]
    assert tasks["scheduled"]["depends"] == [
        f"check:{c.id}" for c in checks if c.when in ("schedule", "both")
    ]
    assert "check:links-online" not in tasks["ci"]["depends"]
    assert "check:vulns" in tasks["scheduled"]["depends"]
    assert tasks["check"]["depends"] == [
        "ci",
        "check:component:api",
        "check:component:web",
    ]
    for c in rendered.principles["components"]:
        task = tasks[f"check:component:{c['name']}"]
        assert task["dir"] == c["path"]
        assert task["run"] == [cmd for _, cmd in check_commands(c["commands"])]


def test_root_component_task_runs_at_the_root(tmp_path: Path):
    tasks = mise(tmp_path, "python-ml-single")["tasks"]
    assert tasks["check:component:ml"]["dir"] == "."
    assert "check:migrations" not in tasks
    assert "check:squawk" not in tasks


def test_repo_checks_skip_vendored_dirs(tmp_path: Path):
    out = texts(tmp_path, "web-ts-plus-python-api")
    typos = tomllib.loads(out["_typos.toml"])["files"]["extend-exclude"]
    rumdl = tomllib.loads(out[".rumdl.toml"])["global"]["exclude"]
    lychee = tomllib.loads(out["lychee.toml"])["exclude_path"]
    for globs in (typos, rumdl):
        assert "web/**/node_modules/" in globs
        assert "api/**/.venv/" in globs
        assert ".claude/alpha/state/" in globs
        assert "api/uv.lock" in globs
        assert "web/pnpm-lock.yaml" in globs
        assert not any(g.startswith("!") for g in globs)
    assert "CHANGELOG.md" in typos
    assert "CHANGELOG.md" not in rumdl

    # lychee takes regular expressions, matched against the file path.
    def skipped(path: str) -> bool:
        return any(re.search(rx, path) for rx in lychee)

    assert skipped("./web/node_modules/pkg/README.md")
    assert skipped("./web/src/node_modules/pkg/README.md")
    assert skipped("./api/.venv/lib/README.md")
    assert skipped("./.claude/alpha/state/notes.md")
    assert not skipped("./docs/architecture.md")
    assert not skipped("./web/README.md")
    assert not skipped("./CHANGELOG.md")


def test_root_component_excludes_match_any_depth(tmp_path: Path):
    out = texts(tmp_path, "python-ml-single")
    typos = tomllib.loads(out["_typos.toml"])["files"]["extend-exclude"]
    lychee = tomllib.loads(out["lychee.toml"])["exclude_path"]
    assert ".venv/" in typos
    assert any(re.search(rx, "./sub/.venv/x.md") for rx in lychee)
    assert not any(re.search(rx, "./venv.md") for rx in lychee)


def test_rumdl_leaves_paragraph_length_alone(tmp_path: Path):
    # alpha writes one line per paragraph on purpose; headings and code
    # blocks keep the 80-column limit.
    text = texts(tmp_path, "rust-cli")[".rumdl.toml"]
    assert tomllib.loads(text)["MD013"] == {"paragraphs": False}
    assert "one line per paragraph" in text
