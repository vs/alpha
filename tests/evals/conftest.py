import json
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hooks take machine-wide slots under HOME; keep them off the real one."""
    real = Path.home() / ".gitconfig"
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    if "GIT_CONFIG_GLOBAL" not in os.environ and real.is_file():
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(real))


@pytest.fixture
def stub_tools(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
):
    """Stand-in uv and pnpm that log each call and succeed; python3 is this one."""
    bin_dir = tmp_path_factory.mktemp("bin")
    log = bin_dir / "tools.log"
    for tool in ("uv", "pnpm"):
        script = bin_dir / tool
        script.write_text(f'#!/bin/sh\necho "$(basename "$PWD"): {tool} $*" >> {log}\n')
        script.chmod(0o755)
    (bin_dir / "python3").symlink_to(sys.executable)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return log


def snapshot(project: Path) -> dict[str, bytes]:
    return {
        p.relative_to(project).as_posix(): p.read_bytes()
        for p in project.rglob("*")
        if p.is_file()
        and not p.relative_to(project)
        .as_posix()
        .startswith((".git/", ".claude/alpha/state/"))
        and "__pycache__" not in p.parts
    }


FAKE = Path(__file__).with_name("fake_claude.py")


class FakeClaude:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.command = (sys.executable, str(FAKE))
        (folder / "replies.jsonl").write_text("")

    def _add(self, reply: dict) -> None:
        with (self.folder / "replies.jsonl").open("a") as f:
            f.write(json.dumps(reply) + "\n")

    def reply(self, text, session="s-a", cost=0.01, denials=(), run=None) -> None:
        self._add(
            {
                "stdout": {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": text,
                    "session_id": session,
                    "total_cost_usd": cost,
                    "permission_denials": list(denials),
                },
                "run": run,
            }
        )

    def fail(self, exit=1, stderr="", stdout="") -> None:
        self._add({"stdout": stdout, "exit": exit, "stderr": stderr})

    def calls(self) -> list[dict]:
        path = self.folder / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def fake(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    folder = tmp_path_factory.mktemp("fake-claude")
    monkeypatch.setenv("FAKE_CLAUDE_DIR", str(folder))
    return FakeClaude(folder)
