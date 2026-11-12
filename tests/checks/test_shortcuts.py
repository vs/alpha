import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "project-files" / "checks" / "shortcuts.py"


def repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True
    )


@pytest.mark.parametrize(
    "line",
    [
        "data = f.read()  # shortcut: whole file in memory, stream it past 100 MB",
        "const xs = all(); // shortcut: no paging, page it past 1000 rows",
        "SELECT 1; -- shortcut: one query per row, batch it past 50 users",
        "<!-- shortcut: hand-written table, generate it once it changes weekly -->",
        "/* shortcut: global lock, shard it once two writers contend */",
    ],
)
def test_a_shortcut_with_a_trigger_passes_and_is_listed(
    tmp_path: Path, line: str
) -> None:
    root = repo(tmp_path, {"src/a.txt": f"x\n{line}\n"})
    assert run(root).returncode == 0
    listed = run(root, "--list")
    assert listed.returncode == 0
    assert listed.stdout.startswith("src/a.txt:2, limit: ")
    assert "upgrade: " in listed.stdout
    assert listed.stdout.endswith("1 shortcuts, 0 with no upgrade trigger.\n")


@pytest.mark.parametrize(
    "comment",
    ["# shortcut: no trigger here", "# shortcut: limit, later", "# shortcut:"],
)
def test_a_shortcut_without_a_trigger_fails(tmp_path: Path, comment: str) -> None:
    root = repo(tmp_path, {"app.py": f"x = 1  {comment}\n"})
    r = run(root)
    assert r.returncode == 1
    assert r.stdout.startswith("app.py:1: this shortcut names no upgrade trigger.")
    assert "shortcut: <the limit>, <when to upgrade>" in r.stdout
    assert "no-trigger" in run(root, "--list").stdout


def test_prose_ignored_and_alpha_files_skipped(tmp_path: Path) -> None:
    root = repo(
        tmp_path,
        {
            "README.md": "Mark one with a `shortcut: <limit>, <when>` comment.\n",
            # Split so the repo's own shortcuts check doesn't read them here.
            ".claude/alpha/checks/x.py": "#" + " shortcut: nothing\n",
            "ignored/b.py": "#" + " shortcut: nothing\n",
            ".gitignore": "ignored/\n",
        },
    )
    assert run(root).returncode == 0
    assert run(root, "--list").stdout == "No shortcuts. Clean ledger.\n"
