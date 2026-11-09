import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "project-files" / "checks" / "review_dates.py"

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
    assert "osv-scanner.toml" in r.stdout


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
