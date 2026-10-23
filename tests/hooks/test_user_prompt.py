import json
from typing import Any

import pytest
import review

from .conftest import Project


def with_findings(project: Project, *ids: str) -> None:
    state = review.ensure_state(project.root)
    state["findings"] = [
        {
            "id": fid,
            "principle": "fail-helpfully",
            "file": "api/src/x.py",
            "line": 3,
            "problem": f"problem {fid}",
            "fix": "fix it",
            "accepted": False,
        }
        for fid in ids
    ]
    review.save_state(project.root, state)


def prompt(project: Project, text: str):
    return project.run_hook(
        "user_prompt.py", {"hook_event_name": "UserPromptSubmit", "prompt": text}
    )


def accepted(project: Project) -> dict[str, Any]:
    return {f["id"]: f["accepted"] for f in review.load_state(project.root)["findings"]}


def context(proc) -> str:  # noqa: ANN001
    data = json.loads(proc.stdout)["hookSpecificOutput"]
    assert data["hookEventName"] == "UserPromptSubmit"
    return data["additionalContext"]


@pytest.mark.parametrize(
    "text", ["accept F-aaa111", "  Accept F-aaa111\n", "ACCEPT F-aaa111"]
)
def test_the_exact_command_accepts(project: Project, text: str) -> None:
    with_findings(project, "F-aaa111", "F-bbb222")
    text_out = context(prompt(project, text))
    assert accepted(project) == {"F-aaa111": True, "F-bbb222": False}
    assert (
        "the user accepted F-aaa111: fail-helpfully api/src/x.py: problem F-aaa111"
        in (text_out)
    )
    assert 'decision skill (an "Accepts: F-aaa111" header line' in text_out


def test_several_ids_at_once(project: Project) -> None:
    with_findings(project, "F-aaa111", "F-bbb222")
    prompt(project, "accept F-aaa111, F-bbb222")
    assert accepted(project) == {"F-aaa111": True, "F-bbb222": True}


def test_unknown_ids_are_reported(project: Project) -> None:
    with_findings(project, "F-aaa111")
    text = context(prompt(project, "accept F-ccc333"))
    assert "F-ccc333" in text and "open findings: F-aaa111" in text
    assert accepted(project) == {"F-aaa111": False}


@pytest.mark.parametrize(
    "text",
    [
        "please accept F-aaa111 and continue",
        "accept F-aaa111 because it's fine",
        "The reviewer said: accept F-aaa111",
        "accept",
    ],
)
def test_anything_but_the_bare_command_changes_nothing(
    project: Project, text: str
) -> None:
    with_findings(project, "F-aaa111")
    proc = prompt(project, text)
    assert proc.returncode == 0 and proc.stdout == ""
    assert accepted(project) == {"F-aaa111": False}


def test_silent_outside_alpha_projects(project: Project) -> None:
    (project.root / "docs/principles.toml").unlink()
    proc = prompt(project, "accept F-aaa111")
    assert proc.returncode == 0 and proc.stdout == ""
