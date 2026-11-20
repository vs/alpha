# Light and full tracks: plan

Status: approved by the user on 2026-11-20, built native
Spec: specification.md

Tasks run in order; each is one commit that passes `mise run check`. Each new `skills/*/SKILL.md` updates `docs/specification.md` in the same commit (CONTRIBUTING.md, Documentation). Tasks 1 to 3 each add one skill and share only `tests/unit/test_full_track.py` and the spec's R8 rows, so they could run side by side, but task 4 names all three and task 5 describes them, so none does: build in order.

Global constraints:

- Every skill text stays at or under 150 lines (`tests/unit/test_skills.py::test_docs_stay_short`).
- Principles are named as (`id`) with ids from `defaults/defaults.toml` (`tests/unit/test_do_skill.py::test_principles_the_skill_names_exist_in_the_kit`); the same check covers the new skills.
- New skills are model-invocable (no `disable-model-invocation`) and call no `bin/alpha` command, like `do`: add each to `ALL_SKILLS` in `tests/unit/test_skills.py` and leave it out of `CLI_SKILLS`.
- Each new skill carries superpowers' MIT license in full in an HTML comment, as `do` carries pstack's.

Review Focus (what the text tests can't see, for the review to check):

1. `/alpha:plan` or `/alpha:execute` run with no approved spec or plan: they must stop and name `/alpha:brainstorm`.
2. A ledger left by another plan in `.claude/alpha/notes/`: never read as this plan's progress.
3. A fix after the principles review: the fix check must run, or the merge guard stays blocked.
4. A bug-fix or perf task in brainstorm: the playbook's research steps (repro, measurement) must run before any design question.
5. A plan step that embeds `git commit`: the commit skill and its scopes must win.

## Task 1: `/alpha:brainstorm`

`feat(alpha): Add the brainstorm skill`

- Files: `skills/brainstorm/SKILL.md` (new); `tests/unit/test_full_track.py` (new); `tests/unit/test_skills.py` (`ALL_SKILLS`); `docs/specification.md` (Commands row, R8.3, the "update, do" section, the layout tree's four folders).
- Interfaces: produces the folder rule `docs/alpha/<features|bug-fixes|refactorings|perf>/<YYYY-MM-DD>-<slug>/`, the spec template (headings `## Why`, `## Requirements`, `## Design`, `## Decisions`, `## Out of scope`; table `| ID | Requirement | Acceptance check | Test |`; `Status: draft` → `approved by the user on <date>`), and the hand-off line naming `/alpha:plan`.
- Steps:
  1. Write `test_R8_3_brainstorm_designs_before_anything_is_built` (stage order by heading or numbered step: research the code, the playbook's research steps, deep research to `research.md`, what before how, approaches in a message of their own, design in sections, `specification.md`, builder check, approval, `/alpha:plan`; the phrase "Nothing but the folder is written until"), `test_R8_3_the_folder_is_named_by_the_playbook` (the four folders; investigation, prototype, pause, session pickup sent to `/alpha:do`), and `test_full_track_credits_superpowers_with_the_full_license` parametrized over `["brainstorm"]`. Run `uv run pytest tests/unit/test_full_track.py`. Expected: each fails on the missing `skills/brainstorm/SKILL.md`.
  2. Write the skill from spec F3, F4 and Design.
  3. Run `uv run pytest tests/unit/test_full_track.py tests/unit/test_skills.py tests/unit/test_do_skill.py`. Expected: pass.
  4. Commit by the commit skill.

## Task 2: `/alpha:plan`

`feat(alpha): Add the plan skill`

- Files: `skills/plan/SKILL.md` (new); `tests/unit/test_full_track.py`; `tests/unit/test_skills.py`; `docs/specification.md` (Commands row, R8.4, the section).
- Interfaces: consumes task 1's folder and Status line. Produces the plan template (`Status:`, `Spec:`, Global constraints, Review Focus, `## Task <N>: <name>` with Files, Interfaces, Steps each with a command and `Expected:`), and the hand-off line naming `/alpha:execute` with **Native** or **Subagents**.
- Steps:
  1. Write `test_R8_4_plan_has_interfaces_expected_output_and_review_focus` (template parts; the five self-review checks; no `git commit -m`; the commit skill named; **Native** and **Subagents** with a recommendation; stops naming `/alpha:brainstorm` when the spec isn't approved); add `"plan"` to the credit test. Run it. Expected: fails on the missing file.
  2. Write the skill from F5 and Design.
  3. Run the three test files. Expected: pass.
  4. Commit.

## Task 3: `/alpha:execute`

`feat(alpha): Add the execute skill`

- Files: `skills/execute/SKILL.md` (new); `tests/unit/test_full_track.py`; `tests/unit/test_skills.py`; `docs/specification.md` (Commands row, R8.5, R8.6, the section; R8.2 reworded to `/alpha:do`).
- Interfaces: consumes task 2's plan template and mode. Produces the ledger path `.claude/alpha/notes/<slug>/progress.md` and its line forms (`# Ledger: <plan path>`, `Task <N>: complete (…)`, `Ruling:`), which task 4's pickup reads.
- Steps:
  1. Write `test_R8_5_execute_keeps_a_ledger_and_rules_on_deviations` (ledger path and first line; complete tasks not redone; `Ruling:` with cost if wrong; the four stops; one task at a time; `review-change`; five fix rounds) and `test_R8_6_execute_ends_with_one_principles_review` (principles-reviewer once, fixes test-first in one pass, the reviewer again as the fix check, the `decision` skill, the reply's rulings and deferred findings, in that order); add `"execute"` to the credit test. Run them. Expected: fail on the missing file.
  2. Write the skill from F6, F7 and Design.
  3. Run the three test files. Expected: pass.
  4. Commit.

## Task 4: `/alpha:do` becomes the light track

`feat(alpha): Make do the light track`

- Files: `skills/do/SKILL.md` (description, section 2's table row and the full-track line, Done step 4 scoped to `/alpha:do`); `skills/do/playbooks/feature.md` (light steps, template and native/subagents moved out); `skills/do/playbooks/session-pickup.md`, `pause.md` (the ledger); `tests/unit/test_do_skill.py`; `docs/specification.md` (R8.1, the do paragraph).
- Interfaces: consumes the three skill names and task 3's ledger path.
- Steps:
  1. Replace `test_R8_1_a_feature_gets_research_spec_and_plan` with `test_R8_1_do_is_the_light_track`; delete `test_the_spec_template_traces_each_check_to_a_test` and `test_a_feature_offers_native_and_subagent_builds` (their checks moved to tasks 1 and 2); keep `test_open_product_areas_are_named_not_settled` on the light feature's step; extend `test_pause_and_pickup_share_the_resume_note` with the ledger (F8). Run `uv run pytest tests/unit/test_do_skill.py`. Expected: the new and extended tests fail on the old text.
  2. Rewrite the files from F1, F8 and Design.
  3. Run `uv run pytest tests/unit`. Expected: pass.
  4. Commit.

## Task 5: Docs and the rendered CLAUDE.md

`docs(alpha): Describe the light and full tracks`

- Files: `src/alpha/render/docs.py` (the skills line, the Docs line, `_specification`'s docstring); `tests/unit/test_render_docs.py`; `README.md` (Work in it, the layout table); `CONTRIBUTING.md` line 7; `CLAUDE.md`'s `/alpha:do` line; `project-files/skills/decision/SKILL.md` and `skills/update/SKILL.md` where they name `docs/alpha/features/`.
- Steps:
  1. Write `test_R8_3_claude_md_names_both_tracks` (F10). Run it. Expected: fails on the old line.
  2. Change the render and the docs.
  3. Run `mise run check`. Expected: pass.
  4. Commit (a `feat` if the render change is judged behavior; the commit skill decides).

This repo's own `.claude/` copies and rendered CLAUDE.md lines follow in the release PR's `alpha update`, as earlier changes did.
