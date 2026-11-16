import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[3] / "project-files" / "checks" / "review_dates.py"

OSV_GOOD = (
    '[[IgnoredVulns]]\nid = "GHSA-aaaa-bbbb-cccc"\nignoreUntil = 2026-12-31\n'
    'reason = "no fix released yet"\n'
)
BL_GOOD = "# test fixture token (review 2026-12-31)\na.py:github-pat:3\n"


def run(cwd: Path, today: str = "2026-11-09") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--today", today],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def osv(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "osv-scanner.toml").write_text(body)
    return run(tmp_path)


def test_no_files_passes(tmp_path: Path) -> None:
    assert run(tmp_path).returncode == 0


def test_osv_missing_ignore_until_fails(tmp_path: Path) -> None:
    r = osv(tmp_path, '[[IgnoredVulns]]\nid = "X-1"\nreason = "no fix yet"\n')
    assert r.returncode == 1
    assert "osv-scanner.toml:1" in r.stdout
    assert "ignoreUntil" in r.stdout


def test_impossible_date_fails(tmp_path: Path) -> None:
    r = osv(tmp_path, OSV_GOOD.replace("2026-12-31", "2026-02-31"))
    assert r.returncode == 1
    assert "not a real date" in r.stdout
    assert "osv-scanner.toml:3" in r.stdout


def test_impossible_string_date_fails(tmp_path: Path) -> None:
    r = osv(tmp_path, OSV_GOOD.replace("2026-12-31", '"2026-02-31"'))
    assert r.returncode == 1
    assert "not a real date" in r.stdout


def test_past_date_fails(tmp_path: Path) -> None:
    (tmp_path / "osv-scanner.toml").write_text(
        OSV_GOOD.replace("2026-12-31", "2026-11-30")
    )
    r = run(tmp_path, today="2026-12-01")
    assert r.returncode == 1
    assert "review date passed" in r.stdout


def test_one_word_reason_fails(tmp_path: Path) -> None:
    r = osv(tmp_path, OSV_GOOD.replace("no fix released yet", "later"))
    assert r.returncode == 1
    assert "reason" in r.stdout


def test_betterleaks_good_passes(tmp_path: Path) -> None:
    (tmp_path / ".betterleaksignore").write_text(BL_GOOD)
    assert run(tmp_path).returncode == 0


def test_betterleaks_missing_comment_fails(tmp_path: Path) -> None:
    (tmp_path / ".betterleaksignore").write_text("a.py:github-pat:3\n")
    r = run(tmp_path)
    assert r.returncode == 1
    assert ".betterleaksignore:1" in r.stdout
    assert "(review YYYY-MM-DD)" in r.stdout


def test_betterleaks_trailing_comment_fails(tmp_path: Path) -> None:
    (tmp_path / ".betterleaksignore").write_text(
        "a.py:github-pat:3 # test fixture token (review 2026-12-31)\n"
    )
    r = run(tmp_path)
    assert r.returncode == 1
    assert "line above" in r.stdout


def test_betterleaks_bad_dates_fail(tmp_path: Path) -> None:
    f = tmp_path / ".betterleaksignore"
    f.write_text("# test fixture (review 2026-02-31)\na.py:github-pat:3\n")
    r = run(tmp_path)
    assert r.returncode == 1 and "not a real date" in r.stdout
    f.write_text("# test fixture (review 2026-6-1)\na.py:github-pat:3\n")
    r = run(tmp_path)
    assert r.returncode == 1 and "not a real date" in r.stdout
    f.write_text("# test fixture (review 2026-11-01)\na.py:github-pat:3\n")
    r = run(tmp_path)
    assert r.returncode == 1 and "review date passed" in r.stdout
    f.write_text("# fixture (review 2026-12-31)\na.py:github-pat:3\n")
    r = run(tmp_path)
    assert r.returncode == 1 and "reason" in r.stdout


def test_betterleaks_comment_applies_to_one_entry(tmp_path: Path) -> None:
    (tmp_path / ".betterleaksignore").write_text(BL_GOOD + "b.py:github-pat:4\n")
    r = run(tmp_path)
    assert r.returncode == 1
    assert ".betterleaksignore:3" in r.stdout


def test_good_entries_pass(tmp_path: Path) -> None:
    (tmp_path / ".betterleaksignore").write_text(BL_GOOD)
    r = osv(tmp_path, OSV_GOOD)
    assert r.returncode == 0, r.stdout


def test_invalid_toml_reports_file(tmp_path: Path) -> None:
    r = osv(tmp_path, "[[IgnoredVulns\n")
    assert r.returncode == 1
    assert "osv-scanner.toml" in r.stdout


def test_latin1_files_fail_cleanly(tmp_path: Path) -> None:
    (tmp_path / ".betterleaksignore").write_bytes(
        b"# caf\xe9 fixture (review 2026-12-31)\n"
    )
    (tmp_path / "osv-scanner.toml").write_bytes(b'reason = "caf\xe9"\n')
    r = run(tmp_path)
    assert r.returncode == 1
    assert ".betterleaksignore: not valid UTF-8. Fix: save it as UTF-8" in r.stdout
    assert "osv-scanner.toml: not valid UTF-8. Fix: save it as UTF-8" in r.stdout
    assert "Traceback" not in r.stderr


def test_osv_bom_is_accepted(tmp_path: Path) -> None:
    (tmp_path / "osv-scanner.toml").write_bytes(b"\xef\xbb\xbf" + OSV_GOOD.encode())
    assert run(tmp_path).returncode == 0


def test_osv_header_variants_keep_line_numbers(tmp_path: Path) -> None:
    good = OSV_GOOD.replace("[[IgnoredVulns]]", "[[IgnoredVulns]] # note")
    body = (
        good
        + "\n[Other]\nx = 1\n\n"
        + OSV_GOOD.replace("[[IgnoredVulns]]", '[[ "IgnoredVulns" ]]')
        + "\n"
        + OSV_GOOD.replace("2026-12-31", "2026-11-01")
    )
    r = osv(tmp_path, body)
    assert r.returncode == 1
    bad_line = body.splitlines().index("[[IgnoredVulns]]") + 1
    assert f"osv-scanner.toml:{bad_line}:" in r.stdout
    assert r.stdout.count("\n") == 1


def test_osv_unmatched_headers_omit_line(tmp_path: Path) -> None:
    r = osv(
        tmp_path,
        'IgnoredVulns = [{id = "X-1", ignoreUntil = 2026-12-31}]\n',
    )
    assert r.returncode == 1
    assert "osv-scanner.toml: entry 1" in r.stdout


def test_osv_wrong_format_date_hint(tmp_path: Path) -> None:
    r = osv(tmp_path, OSV_GOOD.replace("2026-12-31", "2026-6-1"))
    assert r.returncode == 1
    assert (
        "osv-scanner.toml:3: ignoreUntil is not a real date; write YYYY-MM-DD"
        in r.stdout
    )


def test_osv_future_datetime_passes(tmp_path: Path) -> None:
    r = osv(tmp_path, OSV_GOOD.replace("2026-12-31", "2026-12-31T10:00:00Z"))
    assert r.returncode == 0, r.stdout


def test_osv_invalid_toml_has_line(tmp_path: Path) -> None:
    r = osv(tmp_path, "a = 1\nb = [\n")
    assert r.returncode == 1
    assert "osv-scanner.toml:" in r.stdout
    assert any(ch.isdigit() for ch in r.stdout.split(":")[1])


def test_osv_ignored_vulns_not_a_list(tmp_path: Path) -> None:
    r = osv(tmp_path, "IgnoredVulns = 5\n")
    assert r.returncode == 1
    assert "array of tables" in r.stdout
    assert "Traceback" not in r.stderr


def test_betterleaks_tab_comment_is_trailing(tmp_path: Path) -> None:
    (tmp_path / ".betterleaksignore").write_text(
        "a.py:github-pat:3\t# x y (review 2026-12-31)\n"
    )
    r = run(tmp_path)
    assert r.returncode == 1 and "line above" in r.stdout


def test_bad_today_goes_to_stderr(tmp_path: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--today", "nope"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1 and "not a real date" in r.stderr and not r.stdout


def test_osv_file_next_to_a_lockfile_is_checked(tmp_path: Path) -> None:
    # osv-scanner loads <lockfile dir>/osv-scanner.toml, so that one counts.
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "osv-scanner.toml").write_text(
        OSV_GOOD.replace("2026-12-31", "2026-11-30")
    )
    r = run(tmp_path, today="2026-12-01")
    assert r.returncode == 1
    assert "api/osv-scanner.toml:1: GHSA-aaaa-bbbb-cccc ignoreUntil" in r.stdout
    assert "review date passed" in r.stdout


def test_every_osv_file_is_checked(tmp_path: Path) -> None:
    (tmp_path / "osv-scanner.toml").write_text(OSV_GOOD)
    for folder in ("api", "web"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "osv-scanner.toml").write_text(
            '[[IgnoredVulns]]\nid = "X-1"\nreason = "no fix yet"\n'
        )
    r = run(tmp_path)
    assert r.returncode == 1
    assert "api/osv-scanner.toml:1: X-1 has no ignoreUntil" in r.stdout
    assert "web/osv-scanner.toml:1: X-1 has no ignoreUntil" in r.stdout
    assert "\nosv-scanner.toml" not in "\n" + r.stdout


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_in_a_repository_ignored_osv_files_are_skipped(
    tmp_path: Path, git_env: None
) -> None:
    bad = '[[IgnoredVulns]]\nid = "X-1"\nreason = "no fix yet"\n'
    git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "osv-scanner.toml").write_text(bad)
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "osv-scanner.toml").write_text(bad)  # untracked, not ignored
    r = run(tmp_path)
    assert r.returncode == 1
    assert "api/osv-scanner.toml:1" in r.stdout
    assert "node_modules" not in r.stdout
