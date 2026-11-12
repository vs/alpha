import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypedDict, cast

import pytest

from alpha.cli import PLUGIN_ROOT
from alpha.defaults import Source
from alpha.registry import load_registry
from alpha_evals.seeded import REPO_SEEDS


@pytest.fixture(autouse=True)
def isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hooks take machine-wide slots under HOME; keep them off the real one."""
    real = Path.home() / ".gitconfig"
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    if "GIT_CONFIG_GLOBAL" not in os.environ and real.is_file():
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(real))


def honest_mise() -> str:
    """A mise that passes `run ci` and fails each check:<id> like the real tool."""
    registry = load_registry(Source(PLUGIN_ROOT, True))
    cases = ""
    for check, (tool, _, _, says) in REPO_SEEDS.items():
        pin = registry.tool(tool).pin
        assert pin is not None
        cases += f"  check:{check}) echo {says!r}; exit {pin.fails_with};;\n"
    return f'#!/bin/sh\ncase "$2" in\n{cases}  *) exit 0;;\nesac\n'


@pytest.fixture
def stub_tools(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    bin_dir = tmp_path_factory.mktemp("bin")
    log = bin_dir / "tools.log"
    for tool in ("uv", "pnpm"):
        script = bin_dir / tool
        script.write_text(f'#!/bin/sh\necho "$(basename "$PWD"): {tool} $*" >> {log}\n')
        script.chmod(0o755)
    (bin_dir / "python3").symlink_to(sys.executable)
    (bin_dir / "mise").write_text(honest_mise())
    (bin_dir / "mise").chmod(0o755)
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


class Call(TypedDict):
    argv: list[str]
    cwd: str
    stdin: str


class FakeClaude:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.command = (sys.executable, str(FAKE))
        (folder / "replies.jsonl").write_text("")

    def add(self, reply: dict[str, Any]) -> None:
        with (self.folder / "replies.jsonl").open("a") as f:
            f.write(json.dumps(reply) + "\n")

    def reply(
        self,
        text: str,
        session: str = "s-a",
        cost: float = 0.01,
        denials: Sequence[dict[str, Any]] = (),
        run: str | None = None,
    ) -> None:
        self.add(
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

    def fail(self, exit: int = 1, stderr: str = "", stdout: str = "") -> None:
        self.add({"stdout": stdout, "exit": exit, "stderr": stderr})

    def calls(self) -> list[Call]:
        path = self.folder / "calls.jsonl"
        if not path.exists():
            return []
        return [cast(Call, json.loads(line)) for line in path.read_text().splitlines()]


@pytest.fixture
def fake(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> FakeClaude:
    folder = tmp_path_factory.mktemp("fake-claude")
    monkeypatch.setenv("FAKE_CLAUDE_DIR", str(folder))
    return FakeClaude(folder)
