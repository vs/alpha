import pytest

from alpha.generate import GenerateError
from alpha.merge import Change, classify, merge3

BASE = "one\ntwo\nthree\nfour\nfive\nsix\n"


def test_separate_edits_merge_cleanly() -> None:
    ours = BASE.replace("one", "ONE")
    theirs = BASE.replace("five", "FIVE")
    text, conflicted = merge3(BASE, ours, theirs)
    assert not conflicted
    assert "ONE" in text and "FIVE" in text


def test_same_line_conflicts_with_three_labels() -> None:
    text, conflicted = merge3(
        BASE, BASE.replace("two", "mine"), BASE.replace("two", "alpha's")
    )
    assert conflicted
    for marker in ("<<<<<<< yours", "||||||| before", "=======", ">>>>>>> alpha"):
        assert marker in text


def test_untouched_file_takes_alphas_version() -> None:
    theirs = BASE.replace("three", "3")
    assert merge3(BASE, BASE, theirs) == (theirs, False)


def test_non_ascii_survives() -> None:
    base = "Grüße — ok\nb\nc\nd\ne\n"
    ours = base.replace("\nb\n", "\nB — ä\n")
    theirs = base.replace("\ne\n", "\nE\n")
    text, conflicted = merge3(base, ours, theirs)
    assert not conflicted
    assert text == "Grüße — ok\nB — ä\nc\nd\nE\n"


def test_missing_final_newline_survives() -> None:
    text, conflicted = merge3("a\nb", "a\nb", "a\nB")
    assert (text, conflicted) == ("a\nB", False)


def test_merge3_without_git_names_the_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(GenerateError, match="Install git"):
        merge3("a\n", "b\n", "c\n")


def test_classify_new() -> None:
    assert classify("f", None, "A\n", None) == Change("f", "new", "A\n")


def test_classify_conflict_when_disk_exists_without_before() -> None:
    change = classify("f", None, "A\n", "B\n")
    assert change is not None and change.kind == "conflict"
    assert change.text is not None and "<<<<<<< yours" in change.text


def test_classify_change() -> None:
    assert classify("f", "x\n", "y\n", "x\n") == Change("f", "change", "y\n")


def test_classify_merge() -> None:
    base = BASE
    change = classify(
        "f", base, base.replace("five", "FIVE"), base.replace("one", "ONE")
    )
    assert change is not None and change.kind == "merge"
    assert change.text is not None and "ONE" in change.text and "FIVE" in change.text


def test_classify_conflict() -> None:
    change = classify("f", "x\n", "y\n", "z\n")
    assert change is not None and change.kind == "conflict"
    assert change.text is not None and ">>>>>>> alpha" in change.text


def test_classify_skipped() -> None:
    assert classify("f", "x\n", "y\n", None) == Change("f", "skipped", None)


def test_classify_stale() -> None:
    assert classify("f", "x\n", None, "x\n") == Change("f", "stale", None)


def test_classify_no_change_cases() -> None:
    assert classify("f", None, "A\n", "A\n") is None
    assert classify("f", "x\n", "x\n", "edited\n") is None
    assert classify("f", "x\n", "x\n", None) is None
    assert classify("f", "x\n", None, None) is None
