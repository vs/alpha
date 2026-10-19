import io
import subprocess
import sys
from pathlib import Path
from typing import Any

import _common
import pytest

from .conftest import HOOKS, STUB, Project


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
