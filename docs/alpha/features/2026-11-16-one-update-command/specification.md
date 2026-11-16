# One update command

Date: 2026-11-16
Status: approved by the user on 2026-11-16, built native
Serves: R4.1, R5.2, R7.1, R7.2 and R11.3 in docs/specification.md, which this feature rewrites
Research: research.md · Plan: plan.md

## Why

alpha has three commands for an installed project: `/alpha:update` syncs alpha's files, `/alpha:extend` changes a component or an install answer, `/alpha:specify` settles a product area. They run the same loop and differ only in how the answers change, so the user has to know which of the three a wish belongs to. One `/alpha:update [request]` does all three. Product areas move back into install and update, settled only when the user opts in, since most users can't know them on day one.

## Requirements

<!-- rumdl-disable MD013 -->

| ID | Requirement | Acceptance check | Test |
|---|---|---|---|
| F1 | `/alpha:update` with no request syncs alpha's files to the answers and this kit, as it does today. | Given the update skill, then its sync path runs `update <target> --dry-run`, `update <target>` and `commit <target>` in that order, merges each proposal keeping both sides, and stops with "up to date" when the dry run prints nothing to change. | `tests/unit/test_skills.py::test_R11_3_update_skill_merges_proposals` (unit) |
| F2 | `/alpha:update <change>` changes a component or an install answer, re-asking only what it affects. | Given the update skill, then a change reads `skills/install/areas/<area>.md`, keeps every `overrides` entry, runs the "Revisit the area" loop, bootstraps a new component with `bootstrap <target> --component` and commits; given a hand edit in `CLAUDE.md` and a new component or changed scopes, `alpha update` applies it and keeps the edit. | `tests/unit/test_skills.py::test_R4_1_update_changes_a_component_or_an_install_answer` (unit); `tests/integration/test_update.py::test_R4_1_a_new_component_merges_and_keeps_an_edit` (integration); `tests/integration/test_update.py::test_R4_1_a_changed_answer_merges_and_keeps_an_edit` (integration) |
| F3 | `/alpha:update <product area>` settles the areas it names. | Given the update skill, then settling an area reads its guide in `skills/install/areas/`, researches what the code and docs imply, lays out two or three options and grills with `alpha:grilling`; given ui and performance open, when both are answered, marked done and `alpha update` runs, then their sections are written and their principles are active. | `tests/unit/test_skills.py::test_R7_1_update_settles_the_named_product_areas` (unit); `tests/integration/test_update.py::test_R7_1_settling_areas_writes_their_docs` (integration) |
| F4 | A request with several jobs runs each, then one apply and one commit; an unclear request gets one question. | Given the update skill, then its routing table names the empty, product-area, change, mixed and unclear requests, and the apply and commit steps come once, after every job. | `tests/unit/test_skills.py::test_R11_4_update_routes_each_kind_of_request` (unit) |
| F5 | Install offers each product area once, defaulting to skip; an adoption recommends settling an area the repo's docs describe. | Given `new-project.md` and `adopt.md`, then after the install areas and before the summary each asks per product area with Skip as the default, settles a picked one from its guide, and names `/alpha:update <area>` for the rest; `adopt.md` recommends Settle where the repo's docs describe the area. | `tests/unit/test_skills.py::test_R5_2_install_offers_each_product_area_defaulting_to_skip` (unit) |
| F6 | `answers check` accepts install answers with a product area settled. | Given answers with the ten install areas and performance done and every other product area open, when `alpha answers check` runs, then it prints ok. | `tests/unit/test_answers.py::test_R5_1_a_product_area_may_be_settled_at_install` (unit) |
| F7 | Only install and update read the product guides; `do` names `/alpha:update <area>` and never settles one. | Given the kit's skills, then `skills/install/areas/` holds the twenty area guides, only `install` and `update` files name a product guide, and `do` and its feature playbook name the `/alpha:update <area>` request. | `tests/unit/test_skills.py::test_R7_2_only_install_and_update_settle_product_areas` (unit); `tests/unit/test_do_skill.py::test_open_product_areas_are_named_not_settled` (unit) |
| F9 | The generated `CONTRIBUTING.md` describes the alpha workflow: install once, update as often as needed, do each task, uninstall or purge, and purge removes the description with alpha. | Given a generated project, then `CONTRIBUTING.md` has a "Working with alpha" section right after its title, naming `/alpha:install`, `/alpha:update [request]`, `/alpha:do <task>`, `/alpha:uninstall` and `/alpha:purge` in that order, and in an adopted repo that `/alpha:install` carries out the next step of `docs/alpha/adoption.md`; when `alpha purge` runs, then neither the heading nor any of its lines is left. | `tests/unit/test_render_docs.py::test_R6_1_contributing_describes_the_alpha_workflow` (unit); `tests/unit/test_purge_removers.py::test_R3_2_purge_removes_the_alpha_workflow` (unit) |
| F8 | `/alpha:extend` and `/alpha:specify` are gone, and nothing alpha ships or writes names them. | Given the kit, then `skills/extend/` and `skills/specify/` don't exist, and no file under `skills/`, `project-files/`, `recipes/`, `src/`, `defaults/`, nor `README.md` or `docs/specification.md`, names `/alpha:extend` or `/alpha:specify`; a generated project's specification names `/alpha:update <area>` for each open area. | `tests/unit/test_skills.py::test_no_kit_file_names_a_removed_doc_or_skill` (unit); `tests/integration/test_generate.py` (the open-area tests, integration) |

<!-- rumdl-enable MD013 -->

## Design

No new data and no CLI change: the answers, `areas` and `alpha update` stay as they are. The change is in the skills, the guides' location and the pointer text.

**The update skill** (`skills/update/SKILL.md`), in sections:

1. Target and checks: `<target>` is a folder in `$ARGUMENTS`, else the working directory; `status` must be `installed` or `hooks-off`. `update --dry-run` first: an update waiting to be committed is merged and committed first; answers saved but not applied are shown and applied on a yes.
2. Route the request:

   | Request | Job |
   |---|---|
   | empty | sync: straight to the preview |
   | names a product area | settle it from its guide |
   | names a component or an install answer | change it from its install area's guide, extend's rules |
   | several of these | each job in turn |
   | unclear | one question: which area it belongs to |

3. Settle a product area: research what the code and docs imply and the kit default, two or three options, grilling, `answers write`, `done`, the guide's check.
4. Change a component or an install answer: extend's rules today (current answers as recommendations, `overrides` sent whole, the user moves app code with `git mv`), and the "Revisit the area" and "Fix project.json" loop.
5. Preview and confirm: the dry run's list, the diffs of `CLAUDE.md`, `CONTRIBUTING.md`, `docs/alpha/principles.toml` and the specification, each conflict, and a kit upgrade named before the yes.
6. Apply and merge, bootstrap new or moved components, ask before deleting stale files, commit, report (a new session to load the rules, the areas still open, a drafted recipe to save).

**Install**: after the ten install areas and before the summary, `new-project.md` and `adopt.md` ask per product area, in `areas.PRODUCT_AREAS` order and only for areas that can apply (the guides' own "ask nothing" rule for UI, accessibility, design language and data), `Settle <area> now, or skip it for later?`, Skip recommended. In an adoption, Settle is recommended for an area the repo's docs describe, naming the doc. A picked area is settled as update's section 3 says. The summary and the final report list the settled areas and each open one with its `/alpha:update <area>` request. `install/SKILL.md`'s rule "never settle one here" becomes "settle one only when the user picks it".

**Files**: the ten product guides move from `skills/specify/areas/` to `skills/install/areas/`; `skills/extend/` and `skills/specify/` are deleted. Every guide's "Before you start" names `/alpha:install` and `/alpha:update` as its readers.

**Pointers**: `/alpha:specify <area>` becomes `/alpha:update <area>` and `/alpha:extend` becomes `/alpha:update` in the rendered specification and CLAUDE.md, the CLI's messages, the palette check, the copied decision skill, the `performance-budgets` statement, `do`, README and `docs/specification.md`. A project picks the new text up on its next `/alpha:update`, which merges it as a kit change and replaces the copied decision skill.

**CONTRIBUTING.md**: `render/docs.py`'s `_contributing` adds, right after `# Contributing`, a section every line of which names an `/alpha:` command, so purge's line remover takes it out whole:

<!-- rumdl-disable MD013 -->
<!-- The rendered section's lines are literal text, one line per item. -->

```markdown
## Working with alpha

- `/alpha:install` set up this process once.
- `/alpha:update [request]` keeps it current: with no request it brings alpha's files to the installed kit; with one it adds or changes a component or a setup answer, or settles a product area (`/alpha:update performance`).
- `/alpha:do <task>` works each task by a playbook; a feature goes through research, a spec and a plan the user approves before any code.
- `/alpha:uninstall` switches alpha's hooks off and `/alpha:install` switches them back on; `/alpha:purge` removes alpha in one commit.
```

<!-- rumdl-enable MD013 -->

In an adopted repo the first item reads: "`/alpha:install` adopted this repo on `alpha/adopt`; run again, it carries out the next step of `docs/alpha/adoption.md`."

**For callers**: `/alpha:extend` and `/alpha:specify` stop existing when the plugin updates, a breaking change, so the next release is 2.0.0 (CONTRIBUTING.md, Releases) and its notes say to use `/alpha:update <request>`.

## Decisions

- Install asks per product area, each defaulting to Skip (the user's choice over one multi-select question or asking nothing).
- In an adoption, Settle is recommended where the repo's docs already describe the area, since those docs show the user knows it (Claude's choice).
- All twenty area guides live in `skills/install/areas/`, the one folder both readers use (Claude's choice; confirmed with the user's yes to the file layout).
- The pointer reads `/alpha:update <area>` with the area's plain name (`/alpha:update design language`), matching the form `/alpha:specify` used (Claude's choice).
- The routing stays in one SKILL.md rather than per-job files: the guides already hold each job's questions, and what's left per job is a few lines (Claude's choice, from the research).
- The 2.0.0 bump happens in the release PR, not in this feature.
- `CONTRIBUTING.md` describes the alpha workflow (the user's request), as its first section, so a reader meets how the process runs before its details; every line names an `/alpha:` command so purge removes it without a new remover (Claude's choice of placement and wording).

## Out of scope

- Any change to the CLI, the answers' shape or the merge.
- Re-rendering this repo's own generated docs (`CLAUDE.md`, `docs/alpha/`): the release PR runs `bin/alpha update .` from this checkout.
- Aliases or a deprecation period for `/alpha:extend` and `/alpha:specify`.
- Changing what any area guide asks.
