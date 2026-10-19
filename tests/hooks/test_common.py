from typing import Any

import _common
import pytest

from .conftest import Project


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
