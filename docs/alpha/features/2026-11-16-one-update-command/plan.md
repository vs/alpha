# One update command: plan

Tasks run in order; each is one commit that passes `mise run check`. Tasks 1 to 3 touch `tests/unit/test_skills.py`, so none runs side by side.

## 1. One update skill replaces extend and specify

`feat(alpha): Fold extend and specify into update`

- `skills/update/SKILL.md`: rewritten as the Design's six sections, taking extend's and specify's steps.
- `git mv skills/specify/areas/*.md skills/install/areas/`; each guide's "Before you start" names `/alpha:install` and `/alpha:update`.
- Delete `skills/extend/` and `skills/specify/`.
- `skills/install/SKILL.md` (the `installed` row's pointers), `skills/install/adopt.md` (the "add it later" pointer), `skills/install/areas/components.md` and the other install guides' start lines, `skills/do/SKILL.md`, `skills/do/playbooks/feature.md`: name `/alpha:update`.
- `docs/specification.md`: Commands table, R4.1, R7.1, R7.2, R11.3, the extend/specify/do design, the area-guide paragraph, the skills line of the source tree, the Decisions that name specify. README's command sections.
- Tests: `tests/unit/test_skills.py` (ENTRY, PRODUCT_GUIDES, R11_3, R4_1 and R7_1 skill tests replacing the extend and specify tests, `test_R11_4_update_routes_each_kind_of_request`, R7_2, the guide start-line test, the one-question and answers-write tests), `tests/unit/test_do_skill.py::test_open_product_areas_are_named_not_settled`.
- Makes pass: F1, F2, F3, F4, F7.

## 2. Install offers each product area, defaulting to skip

`feat(alpha): Offer product areas at install`

- `skills/install/SKILL.md` "Rules for every path", `skills/install/new-project.md` (a step between the interview and the summary; the summary and final report), `skills/install/adopt.md` (the same step, Settle recommended where the repo's docs describe the area; the report).
- `docs/specification.md`: R5.1 and R5.2, the install table's `empty` and `existing` rows, the Answers bullet "only specify settles them". README's install part.
- Tests: `tests/unit/test_skills.py::test_R5_2_install_offers_each_product_area_defaulting_to_skip` (replacing `test_R5_2_install_reads_only_install_area_guides`), the final-report test; `tests/unit/test_answers.py::test_R5_1_a_product_area_may_be_settled_at_install` (a guard on current CLI behavior: it passes before the change, which the commit says).
- Makes pass: F5, F6.

## 3. Every pointer names /alpha:update

`feat(alpha): Point at /alpha:update in rendered docs`

- `src/alpha/render/area_docs.py`, `src/alpha/render/docs.py`, `src/alpha/answers.py`, `src/alpha/core_areas.py`, `src/alpha/adopt.py`, `src/alpha/areas.py` (its comment), `project-files/checks/palette.py` (this repo's copy under `.claude/alpha/checks/` follows in the release PR's update), `project-files/skills/decision/SKILL.md`, `defaults/defaults.toml` (`performance-budgets` statement).
- Tests: `tests/unit/test_skills.py::test_no_kit_file_names_a_removed_doc_or_skill` (REMOVED gains `/alpha:extend` and `/alpha:specify`; scan adds `defaults/`, `README.md`, `docs/specification.md`), `tests/integration/test_generate.py`, `tests/integration/test_update.py::test_R7_1_settling_areas_writes_their_docs`, `tests/integration/checks/test_palette.py`, `tests/integration/test_adopt_survey.py`, `tests/integration/test_apply.py`, `tests/unit/test_answers.py` docstring.
- Makes pass: F8.

## 4. CONTRIBUTING.md describes the alpha workflow

`feat(alpha): Describe the alpha workflow in CONTRIBUTING`

- `src/alpha/render/docs.py` (`_contributing`: the "Working with alpha" section after the title, the adopted variant of its first item).
- `docs/specification.md`: R6.1's list of what `CONTRIBUTING.md` holds.
- Tests: `tests/unit/test_render_docs.py::test_R6_1_contributing_describes_the_alpha_workflow`, `tests/unit/test_purge_removers.py::test_R3_2_purge_removes_the_alpha_workflow`; any test that pins `CONTRIBUTING.md`'s first section (`tests/integration/test_apply.py`, `tests/unit/test_render_docs.py`).
- Makes pass: F9.
