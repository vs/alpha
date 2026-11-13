import subprocess
import sys
from pathlib import Path

import pytest
import secret_scan

SCRIPT = Path(__file__).parents[3] / "project-files" / "checks" / "secret_scan.py"
# Stands in for betterleaks: prints the paths it was given, one per line.
PRINT_PATHS = [sys.executable, "-c", "import sys; print(*sys.argv[1:], sep='\\n')"]


def run(cwd: Path, *command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *command], cwd=cwd, capture_output=True, text=True
    )


def repo(path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def write(path: Path, text: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_secret_scan_skips_nested_gitignores(tmp_path: Path, git_env: None) -> None:
    root = repo(tmp_path / "repo")
    write(root / "tracked.md")
    subprocess.run(["git", "add", "tracked.md"], cwd=root, check=True)
    write(root / "new.md")  # untracked, not ignored: scanned
    write(root / ".gitignore", ".env\n")
    write(root / ".env", "KEY=local\n")
    # A folder ignored by its own .gitignore, as .superpowers/ is.
    write(root / ".superpowers/sdd/.gitignore", "*\n")
    write(root / ".superpowers/sdd/notes.md")
    write(root / ".git/info/exclude", "scratch/\n")
    write(root / "scratch/notes.md")
    done = run(root, *PRINT_PATHS)
    assert done.returncode == 0, done.stdout
    assert set(done.stdout.split()) == {"--", "tracked.md", "new.md", ".gitignore"}


def test_secret_scan_passes_a_dash_name_as_a_path(
    tmp_path: Path, git_env: None
) -> None:
    # Read as a flag, this name would make betterleaks pass despite a leak.
    root = repo(tmp_path / "repo")
    write(root / "--exit-code=0")
    done = run(root, *PRINT_PATHS)
    assert done.stdout.split() == ["--", "--exit-code=0"]


def test_secret_scan_keeps_a_failing_batch(
    tmp_path: Path, git_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path / "repo")
    write(root / "a.md")
    write(root / "b.md")
    monkeypatch.chdir(root)
    monkeypatch.setattr(secret_scan, "BATCH", 1)
    fails_on_a = [sys.executable, "-c", "import sys; sys.exit('a.md' in sys.argv)"]
    assert secret_scan.main(fails_on_a) == 1  # a.md's batch runs first


def test_secret_scan_with_no_files_scans_nothing(tmp_path: Path, git_env: None) -> None:
    # Given no paths, betterleaks would scan the whole folder.
    root = repo(tmp_path / "repo")
    done = run(root, sys.executable, "-c", "raise SystemExit(1)")
    assert done.returncode == 0
    assert "nothing to scan" in done.stdout


def test_secret_scan_outside_git_fails_with_a_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    (tmp_path / "plain").mkdir()
    done = run(tmp_path / "plain", *PRINT_PATHS)
    assert done.returncode == 2
    assert "git ls-files failed" in done.stdout
    assert "Run the secrets check from the root of the git repository" in done.stdout


def test_secret_scan_names_a_missing_tool(tmp_path: Path, git_env: None) -> None:
    done = run(repo(tmp_path / "repo"), "no-such-betterleaks", "dir")
    assert done.returncode == 1
    assert "no-such-betterleaks is not installed; run: mise install" in done.stdout
