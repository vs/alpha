import subprocess
from pathlib import Path

import pytest

from .conftest import Project

NO_VERIFY = "--no-verify skips the project's commit checks."
HOOKS_PATH = "Overriding core.hooksPath skips the project's commit checks."
HOOKS_CONFIG = "Changing core.hooksPath switches off the project's commit checks."


def mark_reviewed(project: Project) -> None:
    import review

    state = review.ensure_state(project.root)
    state["reviewed_tree"] = review.snapshot(project.root)
    review.save_state(project.root, state)


def bash(project: Project, command: str) -> subprocess.CompletedProcess[str]:
    return project.run_hook(
        "guard_bash.py", {"tool_name": "Bash", "tool_input": {"command": command}}
    )


@pytest.mark.parametrize(
    ("command", "needle"),
    [
        ("git commit -m x --no-verify", NO_VERIFY),
        ("git commit -nm x", NO_VERIFY),
        ("git commit -anm x", NO_VERIFY),
        ("git commit -n -m x", NO_VERIFY),
        ("git -C sub -c a=b commit --no-verify -m x", NO_VERIFY),
        ("FOO=1 git push --no-verify", NO_VERIFY),
        ("git merge --no-verify topic", NO_VERIFY),
        ("git rebase --no-verify main", NO_VERIFY),
        ("git cherry-pick --no-verify abc", NO_VERIFY),
        ("cd a && git push -f", "-f"),
        ("git push --force", "--force"),
        ("git push origin +main", "+main"),
        ("git push --force-with-lease", "--force-with-lease"),
        ("git push --force-if-includes", "--force-if-includes"),
        ("echo hi; git push -uf origin main", "-uf"),
        ("ls | git push -f", "-f"),
        ("echo hi\ngit push -f", "-f"),
        ("true || command git commit --no-verify", NO_VERIFY),
        ("git push \\\n--force", "--force"),
        ("git commit \\\n--no-verify -m x", NO_VERIFY),
        ("  git push \\\n    --force", "--force"),
        ("  git commit \\\n    --no-verify -m x", NO_VERIFY),
        ("(git push -f)", "-f"),
        ("(cd a && git push -f)", "-f"),
        ("if x; then git push -f; fi", "-f"),
        ("if git push -f; then echo; fi", "-f"),
        ("{ git push -f; }", "-f"),
        ("echo $(git push -f)", "-f"),
        ("! git push -f", "-f"),
        ("time git push -f", "-f"),
        ("for i in 1; do git push -f; done", "-f"),
        ("/usr/bin/git push -f", "-f"),
        ("env FOO=1 git push -f", "-f"),
        ("env -i /usr/bin/git commit --no-verify", NO_VERIFY),
        ("bash -c 'git push -f'", "-f"),
        ('sh -c "cd a && git commit --no-verify"', NO_VERIFY),
        ("bash -lc 'git push -f'", "-f"),
        ("eval 'git push -f'", "-f"),
        ("bash -c \"sh -c 'git push -f'\"", "-f"),
        ("git -c core.hooksPath=/dev/null commit -m x", HOOKS_PATH),
        ("git -c core.hookspath=x push", HOOKS_PATH),
        ("git -ccore.hooksPath=x rebase main", HOOKS_PATH),
        ("git config core.hooksPath /dev/null", HOOKS_CONFIG),
        ("git config --global core.hooksPath ~/hooks", HOOKS_CONFIG),
        ("git config --local core.hookspath x", HOOKS_CONFIG),
        ("git config --unset core.hooksPath", HOOKS_CONFIG),
        ("git config core.hooksPath --unset", HOOKS_CONFIG),
        ("git config core.hooksPath --unset-all", HOOKS_CONFIG),
        ("git config --unset-all core.hooksPath", HOOKS_CONFIG),
        ("git config unset core.hooksPath", HOOKS_CONFIG),
        ("git config set core.hooksPath x", HOOKS_CONFIG),
        ("uv run git commit --no-verify -m x", NO_VERIFY),
        ("uv run --with httpx git push -f", "-f"),
        ("pnpm exec git push --force", "--force"),
        ("npx git commit -n -m x", NO_VERIFY),
        ("nohup git push -f", "-f"),
        ("echo x | xargs git push -f", "-f"),
        ("xargs -I {} git push -f origin {}", "-f"),
        ("nohup uv run git config core.hooksPath x", HOOKS_CONFIG),
    ],
)
def test_blocked(project: Project, command: str, needle: str) -> None:
    result = bash(project, command)
    assert result.returncode == 2, result.stderr
    assert needle in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push -n",
        "git push --dry-run -u origin main",
        'git commit -m "mention --no-verify in text"',
        "git commit -m --no-verify",
        "git commit -mn",
        "echo git push -f",
        "ls -f",
        "git status && git log -n 3",
        "git commit -m 'unbalanced",
        "git push origin main -- +weird",
        "",
        "git -c user.name=x commit -m y",
        "git -c core.hooksPath=x status",
        "bash -c 'echo git push -f'",
        "bash script.sh",
        "echo $(date)",
        "git config core.hooksPath",
        "git config --get core.hooksPath",
        "git config core.hooksPath .claude/alpha/githooks",
        "git config --local core.hooksPath .claude/alpha/githooks/",
        "git config user.name x",
        "uv run pytest",
        "uv run --with httpx python -c 'print(1)'",
        "pnpm exec vitest run",
        "npx tsc --noEmit",
        "nohup sleep 1",
        "xargs echo git push -f",
    ],
)
def test_allowed(project: Project, command: str) -> None:
    mark_reviewed(project)  # these test git rules, not the review checkpoint
    result = bash(project, command)
    assert result.returncode == 0, result.stderr


def test_non_bash_tool_ignored(project: Project) -> None:
    result = project.run_hook(
        "guard_bash.py",
        {"tool_name": "Write", "tool_input": {"command": "git push -f"}},
    )
    assert result.returncode == 0


def test_not_an_alpha_project_ignored(project: Project) -> None:
    (project.root / "docs" / "principles.toml").unlink()
    assert bash(project, "git push -f").returncode == 0


def test_amend_allowed_without_commits(project: Project) -> None:
    assert bash(project, "git commit --amend -m x").returncode == 0


def test_amend_allowed_without_remote(project: Project) -> None:
    project.git("commit", "--allow-empty", "-m", "feat: One")
    assert bash(project, "git commit --amend -m x").returncode == 0


def test_amend_allowed_on_detached_head(project: Project) -> None:
    project.git("commit", "--allow-empty", "-m", "feat: One")
    project.git("checkout", "-q", "--detach")
    assert bash(project, "git commit --amend -m x").returncode == 0


def test_amend_blocked_when_pushed(project: Project, tmp_path: Path) -> None:
    remote = tmp_path.parent / f"{tmp_path.name}-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    project.git("commit", "--allow-empty", "-m", "feat: One")
    project.git("remote", "add", "origin", str(remote))
    project.git("push", "-q", "origin", "HEAD")
    project.git("fetch", "-q", "origin")
    result = bash(project, "git commit --amend --no-edit")
    assert result.returncode == 2
    assert "HEAD is already pushed (" in result.stderr
    assert "origin/" in result.stderr
    assert "Make a new commit instead." in result.stderr
    project.git("commit", "--allow-empty", "-m", "feat: Two")
    assert bash(project, "git commit --amend --no-edit").returncode == 0


@pytest.mark.parametrize(
    ("command", "rel"),
    [
        ("echo x > api/uv.lock", "api/uv.lock"),
        ("echo k >> .env", ".env"),
        ("echo k>.env", ".env"),
        ("cat x | tee api/keys/a.txt", "api/keys/a.txt"),
        ("cat x | tee -a api/keys/a.txt", "api/keys/a.txt"),
        ("sed -i '' 's/a/b/' api/uv.lock", "api/uv.lock"),
        ("sed -i -e s/a/b/ web/pnpm-lock.yaml", "web/pnpm-lock.yaml"),
        ("perl -pi -e 's/a/b/' api/uv.lock", "api/uv.lock"),
        ("cp /tmp/x web/pnpm-lock.yaml", "web/pnpm-lock.yaml"),
        ("mv tmp.lock api/uv.lock", "api/uv.lock"),
        ("rm api/keys/old.txt", "api/keys/old.txt"),
        ("bash -c 'echo x >.env.local'", ".env.local"),
        ("echo x > ./api/../api/uv.lock", "api/uv.lock"),
        ("sed -ni 's/a/b/p' api/uv.lock", "api/uv.lock"),
        ("sed -Ei 's/a/b/' api/uv.lock", "api/uv.lock"),
        ("mv api/uv.lock /tmp/x.lock", "api/uv.lock"),
        ("echo x;>.env", ".env"),
        ("(echo x)>.env", ".env"),
        ("echo x&&>.env", ".env"),
        ("cd api && echo x > uv.lock", "api/uv.lock"),
        ("cd api; rm keys/a.txt", "api/keys/a.txt"),
        ("cd api && cd keys && tee a.txt", "api/keys/a.txt"),
        ("cd -- api && echo x > uv.lock", "api/uv.lock"),
        ("cd -P api; rm uv.lock", "api/uv.lock"),
        ("echo a\\\\ > .env", ".env"),
    ],
)
def test_shell_writes_to_protected_paths_are_blocked(
    project: Project, command: str, rel: str
) -> None:
    proc = bash(project, command)
    assert proc.returncode == 2, (command, proc.stderr)
    assert proc.stderr.startswith(f"{rel} is protected ("), proc.stderr


@pytest.mark.parametrize(
    "command",
    [
        "cat api/uv.lock > /dev/null",
        "grep '>' api/uv.lock",
        'grep ">" api/uv.lock',
        "echo '> api/uv.lock'",
        "uv sync",
        "cp api/uv.lock /tmp/backup.lock",
        "echo x > api/src/app.py",
        "ls 2>&1 api",
        "sed 's/a/b/' api/uv.lock",
        "echo a \\> .env",
        "[[ $x > .env ]] && echo later",
        "cd web && echo x > uv.lock",
    ],
)
def test_reads_and_unprotected_writes_pass(project: Project, command: str) -> None:
    proc = bash(project, command)
    assert proc.returncode == 0, (command, proc.stderr)


def test_write_outside_the_project_passes(
    project: Project, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    proc = bash(project, f"echo x > {outside}/.env")
    assert proc.returncode == 0, proc.stderr


def test_a_cd_out_of_the_project_is_followed(
    project: Project, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    proc = bash(project, f"cd {outside} && echo x > .env")
    assert proc.returncode == 0, proc.stderr


def test_globs_are_matched_against_the_files_they_name(project: Project) -> None:
    project.write(".env.local", "KEY=1\n")
    proc = bash(project, "rm .env*")
    assert proc.returncode == 2
    assert proc.stderr.startswith(".env.local is protected (")
    project.write("api/keys/a.txt", "k\n")
    proc = bash(project, "rm -f api/keys/*.txt")
    assert proc.stderr.startswith("api/keys/a.txt is protected (")


def reviewer(project: Project, command: str) -> subprocess.CompletedProcess[str]:
    return project.run_hook(
        "guard_bash.py",
        {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "agent_id": "a1",
            "agent_type": "principles-reviewer",
        },
    )


@pytest.mark.parametrize(
    "command",
    [
        "python3 .claude/alpha/hooks/review.py brief",
        "git diff HEAD -- api",
        "git log --oneline -5",
        "git show HEAD:api/src/x.py",
        "git status --short 2>/dev/null",
        "cat api/src/x.py | head -20",
    ],
)
def test_the_reviewer_may_read(project: Project, command: str) -> None:
    proc = reviewer(project, command)
    assert proc.returncode == 0, (command, proc.stderr)


@pytest.mark.parametrize(
    "command",
    [
        "echo ok > notes.md",
        "sed -i 's/a/b/' api/src/x.py",
        "git commit -qm 'fix: X'",
        "git stash",
        "git checkout -- api/src/x.py",
        "rm api/src/x.py",
    ],
)
def test_the_reviewer_may_not_change_anything(project: Project, command: str) -> None:
    proc = reviewer(project, command)
    assert proc.returncode == 2, command
    assert "principles-reviewer only reads" in proc.stderr


def test_empty_quoted_argument_does_not_split_the_command(project: Project) -> None:
    proc = bash(project, "git commit -m '' --no-verify")
    assert proc.returncode == 2
    assert NO_VERIFY in proc.stderr


@pytest.mark.parametrize(
    "command",
    [
        "cat > docs/setup.md <<'EOF'\nRun:\ncp .env.example .env\nEOF",
        "cat > notes.md <<EOF\necho KEY=1 > .env\nEOF",
        "git commit -F - <<'EOF'\nfix: X\n\nrm api/uv.lock was wrong\nEOF",
        "git commit -F - <<'EOF'\nfix: Don't use git commit --no-verify\nEOF",
        "cat <<-EOF > docs/x.md\n\trm .env\n\tEOF\necho done",
    ],
)
def test_heredoc_text_is_not_a_command(project: Project, command: str) -> None:
    proc = bash(project, command)
    assert proc.returncode == 0, (command, proc.stderr)


def test_the_heredoc_line_itself_is_still_checked(project: Project) -> None:
    proc = bash(project, "cat > .env <<'EOF'\nKEY=1\nEOF")
    assert proc.returncode == 2
    assert proc.stderr.startswith(".env is protected (")
    proc = bash(project, "cat <<'EOF' | git commit -F - --no-verify\nx\nEOF")
    assert proc.returncode == 2


def committed(project: Project) -> None:
    project.git("add", "-A")
    project.git("commit", "-q", "-m", "chore: Base")
    mark_reviewed(project)


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push --dry-run origin main",
        "gh pr create --fill",
        "gh pr new --fill",
        "gh -R owner/repo pr create --fill",
        "gh --repo=owner/repo pr new",
    ],
)
def test_unreviewed_work_is_not_pushed(project: Project, command: str) -> None:
    committed(project)
    project.write("api/src/x.py", "x = 1\n")
    proc = bash(project, command)
    assert proc.returncode == 2
    assert proc.stderr.startswith(
        "Nothing leaves the machine unreviewed: run the principles-reviewer agent "
        "first (1 file changed since the last review)."
    )


def test_push_allowed_right_after_a_clean_review(project: Project) -> None:
    committed(project)
    project.write("api/src/x.py", "x = 1\n")
    mark_reviewed(project)
    assert bash(project, "git push").returncode == 0


def test_open_findings_block_the_push(project: Project) -> None:
    import review

    committed(project)
    state = review.load_state(project.root)
    state["findings"] = [
        {
            "id": "F-abc123",
            "principle": "p",
            "file": "f",
            "line": 1,
            "problem": "x",
            "fix": "y",
            "accepted": False,
        }
    ]
    review.save_state(project.root, state)
    proc = bash(project, "git push")
    assert proc.returncode == 2
    assert "F-abc123" in proc.stderr


def test_other_git_commands_ignore_review_debt(project: Project) -> None:
    committed(project)
    project.write("api/src/x.py", "x = 1\n")
    for command in ("git status", "git commit -m 'feat: X'", "gh pr view"):
        assert bash(project, command).returncode == 0, command


STATE_MESSAGE = "alpha's hooks keep their state there"


@pytest.mark.parametrize(
    "command",
    [
        "echo '{}' > .claude/alpha/state/review.json",
        "rm .claude/alpha/state/review.json",
        "rm -rf .claude",
        "rm -rf .claude/alpha",
        "sed -i '' 's/false/true/' .claude/alpha/state/review.json",
    ],
)
def test_the_review_state_is_not_writable_from_bash(
    project: Project, command: str
) -> None:
    proc = bash(project, command)
    assert proc.returncode == 2, (command, proc.stderr)
    assert STATE_MESSAGE in proc.stderr


@pytest.mark.parametrize(
    "command", ["git clean -fdX", "git clean -fdx", "git clean -X -f"]
)
def test_git_clean_of_ignored_files_is_blocked(project: Project, command: str) -> None:
    proc = bash(project, command)
    assert proc.returncode == 2
    assert ".claude/alpha/state" in proc.stderr


def test_plain_git_clean_and_reading_the_state_pass(project: Project) -> None:
    assert bash(project, "git clean -fd").returncode == 0
    assert bash(project, "cat .claude/alpha/state/review.json").returncode == 0


SWEEP = "may be the user's or another session's"


@pytest.mark.parametrize(
    ("command", "needle"),
    [
        ("git add -A", "git add -A stages every change"),
        ("git add --all", "git add --all stages every change"),
        ("git add -u", "git add -u stages every change"),
        ("git add --update", "git add --update stages every change"),
        ("git add -Av", "git add -Av stages every change"),
        ("git add .", "git add . stages every change"),
        ("cd api && git add .", "git add . stages every change"),
        ("git add -- .", "git add . stages every change"),
        ("git add ':/'", "git add :/ stages every change"),
        ("git add '*'", "git add * stages every change"),
        ("git commit -am x", "git commit -am commits every tracked change"),
        ("git commit -a -m x", "git commit -a commits every tracked change"),
        ("git commit --all -m x", "git commit --all commits every tracked change"),
        ("git reset --hard", "git reset --hard discards"),
        ("git reset --hard HEAD~1", "git reset --hard discards"),
        ("git checkout .", "git checkout . discards"),
        ("git checkout -- .", "git checkout . discards"),
        ("git checkout HEAD -- .", "git checkout . discards"),
        ("git restore .", "git restore . discards"),
        ("git restore --staged --worktree .", "git restore . discards"),
        ("git stash", "git stash takes"),
        ("git stash -u", "git stash takes"),
        ("git stash push -m wip", "git stash takes"),
        ("git stash pop", "git stash takes"),
        ("git stash drop", "git stash takes"),
        ("bash -c 'git stash'", "git stash takes"),
    ],
)
def test_commands_that_sweep_up_shared_work_are_blocked(
    project: Project, command: str, needle: str
) -> None:
    proc = bash(project, command)
    assert proc.returncode == 2, (command, proc.stderr)
    assert needle in proc.stderr
    assert SWEEP in proc.stderr


@pytest.mark.parametrize(
    "command",
    [
        "git add api/app/main.py docs/guide/upload.md",
        "git add -p api/app/main.py",
        "git add docs/.",
        "git commit -m x",
        "git commit -m 'add -a flag' api/app/main.py",
        "git commit -ma",
        "git reset",
        "git reset HEAD~1",
        "git reset --soft HEAD~1",
        "git checkout main",
        "git checkout -b topic",
        "git checkout docs/principles.toml",
        "git checkout 1a2b3c -- api/migrations/0001_create_uploads.sql",
        "git restore api/app/main.py",
        "git restore --staged .",
        "git stash list",
        "git stash show -p",
    ],
)
def test_commands_that_name_their_files_pass(project: Project, command: str) -> None:
    mark_reviewed(project)
    proc = bash(project, command)
    assert proc.returncode == 0, (command, proc.stderr)
