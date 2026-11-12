import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import HOOKS, OLD_PYTHON, REPO, Project

SCRIPT = HOOKS / "commit_msg.py"
SHIM = REPO / "project-files" / "githooks" / "commit-msg"


def run_msg(
    project: Project,
    message: str,
    *,
    cwd: Path | None = None,
    python: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    msg = project.root / "COMMIT_EDITMSG_TEST"
    msg.write_text(message)
    return subprocess.run(
        [*(python or [sys.executable]), str(SCRIPT), str(msg)],
        cwd=cwd or project.root,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "message",
    [
        "feat(api): Add token refresh\n",
        "fix(api): retarget parse_config\n",
        "docs: Add design doc\n",
        "feat(api)!: Drop v1 routes\n",
        "feat: Embed the viewer\n",
        "feat: Bring back the cache\n",
        "Merge branch 'x'\n",
        'Revert "feat: X"\n',
        "fixup! feat: X\n",
        "squash! feat: X\n",
        "amend! feat: X\n",
        "feat: Add x\n\nBody line.\n",
        "feat: Add x\n\nSee https://example.com/" + "a" * 100 + "\n",
        "feat: Add x\n\nCo-Authored-By: " + "N" * 80 + " <a@b.c>\n",
        "# comment\nfeat: Add x\n# another\n",
        "feat: Add x\n\nBody.\n# ------------------------ >8 ------------------------\n"
        "diff --git a/x b/x\n" + "z" * 200 + "\n",
    ],
)
def test_valid_messages_pass(project: Project, message: str) -> None:
    result = run_msg(project, message)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("message", "fragment"),
    [
        ("feat: Added x\n", "imperative"),
        ("feat: Adding x\n", "imperative"),
        ("feat: Adds x\n", "imperative"),
        ("feat: Add x.\n", "period"),
        ("feat: " + "A" * 51 + "\n", "50"),
        ("feet: Add x\n", "type"),
        ("just some words\n", "type(scope)"),
        ("feat: Add x\nbody right away\n", "blank line"),
        ("feat: Add x\n\n" + "w" * 73 + "\n", "72"),
        ("\n", "empty"),
    ],
)
def test_invalid_messages_fail(project: Project, message: str, fragment: str) -> None:
    result = run_msg(project, message)
    assert result.returncode == 1
    out = result.stdout + result.stderr
    assert out.startswith("commit-msg:")
    assert fragment in out
    assert 'Example: "feat(api): Add token refresh"' in out


def test_description_of_exactly_50_chars_passes(project: Project) -> None:
    assert run_msg(project, "feat: " + "A" * 50 + "\n").returncode == 0


def test_a_scope_off_the_list_passes(project: Project) -> None:
    assert run_msg(project, "fix(poteto-mode): retarget the babysit\n").returncode == 0


def test_a_malformed_scope_is_rejected(project: Project) -> None:
    result = run_msg(project, "feat(Api_v2): Add x\n")
    assert result.returncode == 1
    assert "does not match type(scope): description" in result.stdout + result.stderr


def test_without_principles_uses_defaults_and_any_scope(project: Project) -> None:
    (project.root / "docs" / "principles.toml").unlink()
    assert run_msg(project, "feat(whatever): Add x\n").returncode == 0
    assert run_msg(project, "feet: Add x\n").returncode == 1


def test_old_python_rejects_the_commit(project: Project) -> None:
    # macOS's /usr/bin/python3 is 3.9: skipping the check there would let any
    # message through for everyone whose PATH finds it first.
    result = run_msg(project, "feat: Add x\n", python=OLD_PYTHON)
    assert result.returncode == 1
    assert "alpha needs Python 3.11+ (found 3.9)" in result.stderr


def test_malformed_principles_rejects_the_commit(project: Project) -> None:
    project.write("docs/principles.toml", "schema = = 1")
    result = run_msg(project, "feat: Add x\n")
    assert result.returncode == 1
    assert "not valid TOML" in result.stderr
    assert "git checkout docs/principles.toml" in result.stderr


def test_runs_from_a_subdirectory_using_toplevel_principles(project: Project) -> None:
    data = project.principles()
    data["git"]["types"] = ["feat"]
    project.write_principles(data)
    sub = project.root / "api"
    sub.mkdir()
    assert run_msg(project, "feat(api): Add x\n", cwd=sub).returncode == 0
    assert run_msg(project, "fix(api): Add x\n", cwd=sub).returncode == 1


def test_shim_is_posix_sh_and_executable() -> None:
    assert SHIM.read_text().startswith("#!/bin/sh\n")
    assert SHIM.stat().st_mode & stat.S_IXUSR
    tracked = subprocess.run(
        ["git", "ls-files", "-s", str(SHIM)], cwd=REPO, capture_output=True, text=True
    ).stdout
    assert tracked == "" or tracked.startswith("100755")


def test_shim_blocks_a_bad_commit_end_to_end(project: Project) -> None:
    hooks = project.root / ".claude" / "alpha"
    (hooks / "hooks").mkdir(parents=True)
    (hooks / "githooks").mkdir()
    for name in ("commit_msg.py", "_common.py"):
        (hooks / "hooks" / name).write_text((HOOKS / name).read_text())
    shim = hooks / "githooks" / "commit-msg"
    shim.write_text(SHIM.read_text())
    shim.chmod(0o755)
    project.git("config", "core.hooksPath", ".claude/alpha/githooks")
    project.write("a.txt", "a")
    project.git("add", "a.txt")
    env = {**os.environ}
    bad = subprocess.run(
        ["git", "commit", "-m", "added a"],
        cwd=project.root,
        capture_output=True,
        text=True,
        env=env,
    )
    assert bad.returncode != 0
    assert "commit-msg:" in bad.stdout + bad.stderr
    good = subprocess.run(
        ["git", "commit", "-m", "feat: Add a"],
        cwd=project.root,
        capture_output=True,
        text=True,
        env=env,
    )
    assert good.returncode == 0, good.stdout + good.stderr


def test_dropped_clean_history_accepts_any_message(project: Project) -> None:
    assert run_msg(project, "wip stuff\n").returncode == 1
    project.drop_principle("clean-history")
    result = run_msg(project, "wip stuff\n")
    assert result.returncode == 0, result.stderr


def test_shim_explains_a_missing_python3(
    project: Project, tmp_path_factory: pytest.TempPathFactory
) -> None:
    bin_dir = tmp_path_factory.mktemp("bin")
    git_exe = shutil.which("git")
    assert git_exe is not None
    (bin_dir / "git").symlink_to(git_exe)
    msg = project.write("MSG", "feat: Add x\n")
    done = subprocess.run(
        ["/bin/sh", str(SHIM), str(msg)],
        cwd=project.root,
        capture_output=True,
        text=True,
        env={"PATH": str(bin_dir), "HOME": str(project.root)},
    )
    assert done.returncode == 1
    assert done.stderr.startswith("commit-msg: python3 was not found")
    assert "brew install python" in done.stderr
