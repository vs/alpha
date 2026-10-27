import json
from pathlib import Path

import _common

from .conftest import Project


def record(project: Project, number: int, title: str, status: str = "accepted") -> None:
    slug = title.lower().replace(" ", "-")
    project.write(
        f"docs/decisions/{number:04d}-{slug}.md",
        f"# {number:04d}. {title}\n\nDate: 2026-10-23\nStatus: {status}\n\n"
        "## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nq\n",
    )


def index_lines(project: Project) -> list[str]:
    text = _common.context_text(project.root, project.principles())
    return text.splitlines()


def test_index_lists_records_with_status(project: Project) -> None:
    record(project, 1, "Product identity")
    record(project, 2, "Use OpenAPI")
    records, warnings = _common.decision_index(project.root)
    assert records == [
        (1, "Product identity", "accepted", "docs/decisions/0001-product-identity.md"),
        (2, "Use OpenAPI", "accepted", "docs/decisions/0002-use-openapi.md"),
    ]
    assert warnings == []
    lines = index_lines(project)
    assert lines[0].startswith("alpha: decisions in effect")
    assert "- 0002 Use OpenAPI [accepted] docs/decisions/0002-use-openapi.md" in lines


def test_superseded_record_shows_its_status(project: Project) -> None:
    record(project, 3, "Use REST", status="superseded by 0012")
    assert (
        "- 0003 Use REST [superseded by 0012] docs/decisions/0003-use-rest.md"
        in index_lines(project)
    )


def test_malformed_record_is_skipped_with_a_warning(project: Project) -> None:
    record(project, 1, "Product identity")
    project.write("docs/decisions/notes.md", "just notes\n")
    project.write("docs/decisions/0002-x.md", "# 0002. No status\n")
    records, warnings = _common.decision_index(project.root)
    assert [r[0] for r in records] == [1]
    assert any(
        "docs/decisions/notes.md" in w and "# NNNN. Title" in w for w in warnings
    )
    assert any("docs/decisions/0002-x.md" in w and "Status:" in w for w in warnings)
    assert any("notes.md" in line for line in index_lines(project))


def test_index_caps_at_40_lines(project: Project) -> None:
    for n in range(1, 61):
        record(project, n, f"Decision {n}")
    lines = [x for x in index_lines(project) if x.startswith("- ")]
    shown = [x for x in lines if x.startswith("- 00")]
    assert len(shown) == 40
    assert shown[0].startswith("- 0021 ") and shown[-1].startswith("- 0060 ")
    assert "- … 20 older records in docs/decisions/" in lines


def test_overrides_in_effect(project: Project) -> None:
    lines = _common.overrides_in_effect(project.principles())
    assert len(lines) == 1
    assert lines[0].startswith("observability: active, components ")
    assert lines[0].endswith("-override-observability.md)")
    assert "Principle overrides:" in index_lines(project)


def test_no_records_yet(project: Project) -> None:
    text = _common.context_text(project.root, project.principles())
    assert "no decision records yet" in text


def test_session_start_always_injects_the_index(project: Project) -> None:
    record(project, 1, "Product identity")
    project.git("config", "core.hooksPath", ".claude/alpha/githooks")
    out = project.run_hook("session_start.py", {"hook_event_name": "SessionStart"})
    text = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert text.startswith("alpha: decisions in effect")
    assert "0001 Product identity" in text


def test_subagent_start_injects_the_same_index(project: Project) -> None:
    record(project, 1, "Product identity")
    out = project.run_hook(
        "subagent_start.py",
        {"hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "x"},
    )
    data = json.loads(out.stdout)["hookSpecificOutput"]
    assert data["hookEventName"] == "SubagentStart"
    assert data["additionalContext"] == _common.context_text(
        project.root, project.principles()
    )


def test_subagent_start_is_silent_outside_alpha_projects(project: Project) -> None:
    (project.root / "docs" / "principles.toml").unlink()
    out = project.run_hook("subagent_start.py", {"hook_event_name": "SubagentStart"})
    assert out.returncode == 0 and out.stdout == ""


def test_index_survives_unreadable_files(project: Project, tmp_path: Path) -> None:
    record(project, 1, "Product identity")
    (project.root / "docs/decisions/0002-binary.md").write_bytes(b"\xff\xfe\x00")
    records, warnings = _common.decision_index(project.root)
    assert [r[0] for r in records] == [1]
    assert warnings


def test_override_line_says_what_the_record_changed(project: Project) -> None:
    path = next(
        p["override_decision"]
        for p in project.principles()["principles"]
        if p["override_decision"]
    )
    project.write(
        path,
        "# 0013. Override observability\n\nDate: 2026-10-23\nStatus: accepted\n"
        "Principle: observability (loosen, scope component:api)\n\n## Context\n\nc\n",
    )
    (line,) = _common.overrides_in_effect(project.principles(), project.root)
    assert line == f"observability: loosen, scope component:api ({path})"


def test_a_record_naming_two_principles_reports_each_change(project: Project) -> None:
    path = "docs/decisions/0013-overrides.md"
    project.write(
        path,
        "# 0013. Overrides\n\nDate: 2026-10-23\nStatus: accepted\n"
        "Principle: perf-budgets (drop, scope project)\n"
        "Principle: observability (loosen, scope component:api)\n\n## Context\n\nc\n",
    )
    principles = project.principles()
    for p in principles["principles"]:
        if p["id"] in ("perf-budgets", "observability"):
            p["override_decision"] = path
    lines = _common.overrides_in_effect(principles, project.root)
    assert f"observability: loosen, scope component:api ({path})" in lines
    assert f"perf-budgets: drop, scope project ({path})" in lines


def test_fallback_line_says_only_what_the_file_has(project: Project) -> None:
    principles = project.principles()
    target = next(p for p in principles["principles"] if p["override_decision"])
    del target["active"], target["components"]
    (line,) = _common.overrides_in_effect(principles)
    assert "inactive" not in line and "none" not in line
    assert line.startswith(f"{target['id']}: overridden, see the record (")


def test_a_byte_order_mark_doesnt_hide_the_heading(project: Project) -> None:
    project.write(
        "docs/decisions/0001-bom.md",
        "﻿# 0001. With a BOM\n\nDate: 2026-10-23\nStatus: accepted\n",
    )
    records, warnings = _common.decision_index(project.root)
    assert [r[1] for r in records] == ["With a BOM"] and warnings == []


def test_duplicate_numbers_and_headingless_files_get_clear_warnings(
    project: Project,
) -> None:
    record(project, 1, "Product identity")
    record(project, 1, "Second one")
    project.write("docs/decisions/notes.md", "just notes\n")
    _records, warnings = _common.decision_index(project.root)
    assert any("0001" in w and "more than one record" in w for w in warnings)
    notes = next(w for w in warnings if "notes.md" in w)
    assert "rename it" not in notes and "move it out of docs/decisions/" in notes
