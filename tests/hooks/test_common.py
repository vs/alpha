import ast
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import _common
import pytest
from helpers import single_component, union_annotations

from alpha.answers import load_answers
from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source, load_defaults
from alpha.principles import build_principles

from .conftest import FIXTURE, HOOKS, OLD_PYTHON, STUB, Project


def test_malformed_principles_explains_and_exits_zero(project: Project):
    project.write("docs/principles.toml", "schema = = 1")
    r = project.run_hook(
        "guard_bash.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}}
    )
    assert r.returncode == 0
    assert "not valid TOML" in r.stderr
    assert "git checkout docs/principles.toml" in r.stderr


def test_missing_principles_is_silent(project: Project):
    (project.root / "docs" / "principles.toml").unlink()
    r = project.run_hook("guard_bash.py", {})
    assert r.returncode == 0 and r.stderr == ""


def test_component_for_longest_prefix():
    principles: dict[str, Any] = {
        "components": [{"name": "root", "path": "."}, {"name": "web", "path": "web"}]
    }

    def name(rel: str) -> str | None:
        comp = _common.component_for(rel, principles)
        return comp["name"] if comp else None

    assert name("web/src/a.ts") == "web"
    assert name("README.md") == "root"
    assert name("website/x.ts") == "root"
    assert _common.component_for("a.py", {"components": []}) is None


def test_changed_files_no_commits_and_spaces(project: Project):
    project.write("a b.py")
    assert "a b.py" in _common.changed_files(project.root)


def test_changed_files_tracked_and_state_excluded(project: Project):
    project.write("keep.py", "1")
    project.git("add", "-A")
    project.git("commit", "-qm", "init")
    project.write("keep.py", "2")
    project.write("sub/new.py")
    project.write(".claude/alpha/state/x.json", "{}")
    assert sorted(_common.changed_files(project.root)) == ["keep.py", "sub/new.py"]


def test_matches_double_star():
    g = ["api/src/**/*.py"]
    assert _common.matches("api/src/x/y.py", g)
    assert _common.matches("api/src/y.py", g)
    assert not _common.matches("api/tests/t.py", g)
    assert _common.matches("any/deep/openapi.yaml", ["**/openapi*.yaml"])
    assert _common.matches("docs/principles.toml", ["docs/principles.toml"])


def test_block_exits_2(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as e:
        _common.block("nope")
    assert e.value.code == 2 and "nope" in capsys.readouterr().err


def test_state_path_creates_dir(project: Project):
    p = _common.state_path(project.root, "s.json")
    assert p == project.root / ".claude/alpha/state/s.json" and p.parent.is_dir()


def test_project_root_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Any):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert _common.project_root({"cwd": "/elsewhere"}) == tmp_path
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    assert str(_common.project_root({"cwd": "/elsewhere"})) == "/elsewhere"


def test_changed_files_reports_non_git_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    assert _common.changed_files(tmp_path) == []
    err = capsys.readouterr().err
    assert "could not list changes" in err and "git init" in err


def test_changed_files_reports_missing_git(
    project: Project,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv("PATH", str(project.root / "nowhere"))
    assert _common.changed_files(project.root) == []
    err = capsys.readouterr().err
    assert "could not run git" in err and "git is installed" in err


def test_read_input_malformed_and_non_object(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    for raw in ("{nope", "[1, 2]"):
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        assert _common.read_input() == {}
    assert capsys.readouterr().err.count("alpha: hook input") == 2
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert _common.read_input() == {}


def test_malformed_stdin_does_not_crash_hook(project: Project):
    r = subprocess.run(
        [sys.executable, str(HOOKS / "guard_bash.py")],
        cwd=project.root,
        input="{nope",
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0 and "Traceback" not in r.stderr


def test_fixture_commands_are_stubs_and_unknown_component_rejected(project: Project):
    for comp in project.principles()["components"]:
        assert comp["commands"] and set(comp["commands"].values()) == {STUB}
    project.set_commands("api", test="echo hi")
    assert project.principles()["components"][0]["commands"]["test"] == "echo hi"
    with pytest.raises(KeyError, match="api"):
        project.set_commands("nope", test="x")


def test_project_root_falls_back_to_payload_cwd(project: Project, tmp_path: Path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    r = project.run_hook(
        "guard_bash.py",
        {"cwd": str(project.root)},
        cwd=other,
        env={"CLAUDE_PROJECT_DIR": None},
    )
    assert r.returncode == 0
    project.write("docs/principles.toml", "schema = = 1")
    r = project.run_hook(
        "guard_bash.py",
        {"cwd": str(project.root)},
        cwd=other,
        env={"CLAUDE_PROJECT_DIR": None},
    )
    assert "not valid TOML" in r.stderr


def test_rel_to_root(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    assert _common.rel_to_root(root, str(root / "src" / "a.py")) == "src/a.py"
    assert _common.rel_to_root(root, "src/a.py") == "src/a.py"
    assert _common.rel_to_root(root, str(tmp_path / "other.py")) is None
    assert _common.rel_to_root(root, "../other.py") is None


def test_rel_to_root_resolves_symlinks(tmp_path: Path):
    real = tmp_path / "real"
    (real / "src").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real)
    # root given via the symlink, path via the real location (and vice versa),
    # like /var vs /private/var on macOS
    assert _common.rel_to_root(link, str(real / "src" / "a.py")) == "src/a.py"
    assert _common.rel_to_root(real, str(link / "src" / "a.py")) == "src/a.py"


@pytest.mark.parametrize("hook", sorted(HOOKS.glob("*.py")), ids=lambda p: p.name)
def test_hooks_parse_and_import_on_python_3_9(hook: Path):
    tree = ast.parse(hook.read_text(), str(hook), feature_version=(3, 9))
    assert union_annotations(tree) == [], f"{hook}: needs lazy annotations"


@pytest.mark.parametrize(
    ("script", "payload"),
    [
        ("guard_bash.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}}),
        ("stop_checks.py", {"hook_event_name": "Stop"}),
    ],
)
def test_other_hooks_are_silent_no_ops_on_old_python(
    project: Project, script: str, payload: dict[str, Any]
):
    result = project.run_hook(script, payload, python=OLD_PYTHON)
    assert result.returncode == 0
    assert result.stdout == ""
    assert "alpha needs Python 3.11+ (found 3.9)" in result.stderr


def principles_with(**entries: dict[str, Any]) -> dict[str, Any]:
    return {"principles": [{"id": k, **v} for k, v in entries.items()]}


def test_principle_applies_follows_active_and_components():
    data = principles_with(
        on={"active": True, "components": ["api", "web"]},
        off={"active": False, "components": []},
        scoped={"active": True, "components": ["web"]},
    )
    assert _common.principle_applies(data, "on", "api")
    assert _common.principle_applies(data, "on", None)
    assert not _common.principle_applies(data, "off", "api")
    assert not _common.principle_applies(data, "off", None)
    assert _common.principle_applies(data, "scoped", "web")
    assert not _common.principle_applies(data, "scoped", "api")
    assert _common.principle_applies(data, "scoped", None)


def test_unknown_principle_applies_for_forward_compatibility():
    assert _common.principle_applies({}, "new-principle", "api")
    assert _common.principle_applies(principles_with(), "x", None)


def root_component_principles(tmp_path: Path) -> dict[str, Any]:
    data = json.loads(FIXTURE.read_text())
    data["layout"] = "single"
    single_component(data)
    data["components"][0]["path"] = "."
    data["overrides"] = []
    path = tmp_path / ".claude" / "alpha" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data))
    defaults = load_defaults(Source(PLUGIN_ROOT, True, ""))
    return build_principles(defaults, load_answers(path), "0.1.0")


@pytest.mark.parametrize(
    ("rel", "kind"),
    [
        ("api/main.py", "source"),
        ("api/app/main.py", "source"),
        ("api/src/pkg/core.py", "source"),
        ("api/tests/test_app.py", "test"),
        ("api/test_main.py", "test"),
        ("api/app/conftest.py", "test"),
        ("api/.venv/lib/site.py", None),
        ("api/app/__pycache__/main.py", None),
        ("api/build/lib/main.py", None),
        ("api/README.md", None),
        ("web/app/page.tsx", "source"),
        ("web/src/index.ts", "source"),
        ("web/tests/setup.test.ts", "test"),
        ("web/app/page.test.tsx", "test"),
        ("web/node_modules/zod/index.ts", None),
        ("web/dist/index.ts", None),
        ("web/vitest.config.ts", None),
    ],
)
def test_source_is_every_stack_file_minus_tests_and_generated(
    project: Project, rel: str, kind: str | None
):
    comp = _common.component_for(rel, project.principles())
    assert comp is not None
    got = (
        "source"
        if _common.is_source(rel, comp)
        else "test"
        if _common.is_test(rel, comp)
        else None
    )
    assert got == kind


def test_root_component_ignores_dot_dirs(tmp_path: Path):
    comp = root_component_principles(tmp_path)["components"][0]
    assert _common.is_source("main.py", comp)
    assert not _common.is_source(".claude/alpha/hooks/stop_checks.py", comp)
    assert not _common.is_test(".claude/alpha/hooks/stop_checks.py", comp)
