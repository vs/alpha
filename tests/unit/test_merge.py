import json

import pytest

from alpha.generate import GenerateError
from alpha.merge import Change, classify, merge3, merge_json, union_lines

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


def test_union_lines_keeps_the_repo_and_adds_the_rest() -> None:
    disk = "node_modules/\n.env\n# local\nbuild/"
    merged = union_lines(disk, ".env\n.venv/\n\n.claude/alpha/state/\n")
    assert merged == (
        "node_modules/\n.env\n# local\nbuild/\n"
        "\n# alpha\n.venv/\n.claude/alpha/state/\n"
    )
    assert merged.startswith(disk)


def test_union_lines_nothing_missing_is_unchanged() -> None:
    assert union_lines("a\nb\n", "b\n  a\n") == "a\nb\n"
    assert union_lines("", "a\n") == "# alpha\na\n"


SETTINGS_REPO = {
    "permissions": {"allow": ["Bash(npm test:*)"], "defaultMode": "acceptEdits"},
    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]},
    "env": {"FOO": "1"},
}
SETTINGS_ALPHA = {
    "permissions": {
        "allow": ["Bash(uv run:*)", "Bash(npm test:*)"],
        "deny": ["Bash(git push --force:*)"],
        "defaultMode": "default",
    },
    "hooks": {
        "Stop": [{"hooks": [{"type": "command", "command": "alpha stop"}]}],
        "SessionStart": [{"hooks": [{"type": "command", "command": "alpha start"}]}],
    },
}


def test_merge_json_unions_lists_and_objects() -> None:
    result = merge_json(json.dumps(SETTINGS_REPO), json.dumps(SETTINGS_ALPHA))
    assert result is not None
    merged = json.loads(result[0])
    assert merged["permissions"]["allow"] == ["Bash(npm test:*)", "Bash(uv run:*)"]
    assert merged["permissions"]["deny"] == ["Bash(git push --force:*)"]
    assert [e["hooks"][0]["command"] for e in merged["hooks"]["Stop"]] == [
        "mine",
        "alpha stop",
    ]
    assert "SessionStart" in merged["hooks"] and merged["env"] == {"FOO": "1"}
    again = merge_json(result[0], json.dumps(SETTINGS_ALPHA))
    assert again is not None and json.loads(again[0]) == merged  # no duplicates


def test_merge_json_keeps_repo_scalars_with_a_note() -> None:
    result = merge_json(json.dumps(SETTINGS_REPO), json.dumps(SETTINGS_ALPHA))
    assert result is not None
    text, notes = result
    assert json.loads(text)["permissions"]["defaultMode"] == "acceptEdits"
    assert notes == [
        'permissions.defaultMode: kept yours ("acceptEdits"), alpha\'s is "default"'
    ]


def test_merge_json_invalid_repo_file() -> None:
    assert merge_json("{nope", "{}") is None
    assert merge_json("[1]", "{}") is None


def test_union_lines_keeps_alphas_negations_last() -> None:
    disk = ".env*\n!.env.example\n"
    merged = union_lines(disk, ".env\n.env.*\n**/.env.*\n!.env.example\n")
    assert merged.startswith(disk)
    tail = merged.split("# alpha\n", 1)[1].splitlines()
    assert tail == [".env", ".env.*", "**/.env.*", "!.env.example"]
