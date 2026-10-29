import os
import sys
from pathlib import Path

import pytest


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
