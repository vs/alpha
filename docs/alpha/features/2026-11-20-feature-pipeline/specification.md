# Light and full tracks

Date: 2026-11-20
Status: approved by the user on 2026-11-20, built native
Serves: R8.1 and R8.2 in docs/specification.md, rewritten, and R8.3 to R8.6, new requirements this spec proposes (the user's yes to this spec adds them)
Research: research.md · Plan: plan.md

## Why

The user prefers superpowers' way of working: research, then a design spec, then an implementation plan built from both, then executing that plan, each a skill that hands off to the next. alpha's `/alpha:do` crams those stages into one Feature playbook and offers nothing lighter, while bug fixes, refactorings and perf work never get them. Every task type needs two ways to be done: a light one that goes straight into the work with no files, and a full one that runs the superpowers pipeline under alpha's principles, hooks and principles reviewer, without depending on superpowers.

## Requirements

| ID | Requirement | Acceptance check | Test |
|---|---|---|---|
| F1 | `/alpha:do` is the light track for every task: it writes no research, spec or plan file, and names the full track. | Given the do skill and its playbooks, then none writes `research.md`, `specification.md` or `plan.md`; the router says the full track starts with `/alpha:brainstorm <task>`; the Feature playbook researches the code, states a short design in chat, writes tests that fail first, then the code, and ends with Done. | `tests/unit/test_do_skill.py::test_R8_1_do_is_the_light_track` (unit) |
| F2 | `/alpha:do` runs no whole-branch review. | Given the do skill and its playbooks, then none asks for a review of the whole branch, and Done says the principles review runs when the work reaches main. | `tests/unit/test_do_skill.py::test_R8_2_do_runs_no_whole_branch_review` (unit, kept) |
| F3 | `/alpha:brainstorm <task>` researches, brainstorms with the user and gets a written design approved before anything is built. | Given the brainstorm skill, then in this order it: researches the code and runs the research steps of the task's playbook (a bug's repro and root cause, perf's workload, measurement and baseline, a refactoring's pin); dispatches deep-research subagents and writes `research.md` with sources; asks what the user wants before how, one question at a time; lays out two or three approaches in a message of their own and lets the user pick; plays the design back in sections; writes `specification.md` from the template (a test per acceptance check); runs a builder-check subagent on it; gets the user's approval; then hands off to `/alpha:plan`. It says nothing but the folder is written until the approval. | `tests/unit/test_full_track.py::test_R8_3_brainstorm_designs_before_anything_is_built` (unit) |
| F4 | The full track's folder is named by the task's playbook. | Given the brainstorm skill, then it writes into `docs/alpha/features/`, `docs/alpha/bug-fixes/`, `docs/alpha/refactorings/` or `docs/alpha/perf/` plus `<YYYY-MM-DD>-<slug>/`, by the playbook the task matches, and sends an investigation, prototype, pause or session pickup back to `/alpha:do`. | `tests/unit/test_full_track.py::test_R8_3_the_folder_is_named_by_the_playbook` (unit) |
| F5 | `/alpha:plan` writes a plan an engineer who hasn't seen the code can follow, and gets it approved with the execution mode. | Given the plan skill, then its template has the spec's path, Global Constraints, Review Focus, and `### Task <N>` sections with Files, Interfaces, test-first steps each with a command and its `Expected:` output, and a commit step through the commit skill with no literal `git commit`; it self-reviews for spec coverage, step scan, consistency, Review Focus and proportion; it asks for approval of the plan and for **Native** or **Subagents** with a recommendation; then it hands off to `/alpha:execute`. | `tests/unit/test_full_track.py::test_R8_4_plan_has_interfaces_expected_output_and_review_focus` (unit) |
| F6 | `/alpha:execute` builds the plan without checking in, keeps a ledger it resumes from, and logs every deviation as a ruling. | Given the execute skill, then it keeps `.claude/alpha/notes/<slug>/progress.md`, whose first line names the plan; a task with a `Task <N>: complete` line is never redone; each deviation is a `Ruling:` line with what it costs if wrong; only an irreversible action, a security-sensitive action, a side effect outside the checkout, or a plan broken beyond guessing stops it; in Subagents mode a fresh implementer builds one task at a time and a reviewer runs `review-change` on its diff, with at most five fix rounds. | `tests/unit/test_full_track.py::test_R8_5_execute_keeps_a_ledger_and_rules_on_deviations` (unit) |
| F7 | `/alpha:execute` ends with the principles review, once, and lists its rulings. | Given the execute skill, then after the last task it runs the principles-reviewer agent once over the branch, fixes the findings in one pass with each fix's test failing first, runs the principles-reviewer again as the fix check, records rulings that change what is built in the spec's Decisions with the `decision` skill, and its reply lists every ruling and every deferred finding. | `tests/unit/test_full_track.py::test_R8_6_execute_ends_with_one_principles_review` (unit) |
| F8 | Session pickup resumes a full-track task from its ledger; Pause points to it. | Given the session-pickup playbook, then when a `.claude/alpha/notes/*/progress.md` ledger exists it hands the work to `/alpha:execute`; given the pause playbook, then its resume note names the ledger when there is one. | `tests/unit/test_do_skill.py::test_pause_and_pickup_share_the_resume_note` (unit, extended) |
| F9 | The full-track skills credit superpowers. | Given each of the brainstorm, plan and execute skills, then an HTML comment names superpowers and holds its MIT license in full (`Copyright (c) 2025 Jesse Vincent`). | `tests/unit/test_full_track.py::test_full_track_credits_superpowers_with_the_full_license` (unit) |
| F10 | A project's CLAUDE.md names both tracks and the folders. | Given rendered answers, then CLAUDE.md's skills list says `/alpha:do <task>` works a task straight through and `/alpha:brainstorm <task>` starts the full track (research, a spec and a plan the user approves, then `/alpha:plan` and `/alpha:execute`), and its Docs list names the four folders. | `tests/unit/test_render_docs.py::test_R8_3_claude_md_names_both_tracks` (unit) |

## Design

**Skills.** Three new plugin skills beside `do`, each a `SKILL.md` under `skills/`, model-invocable like `do`:

- `skills/brainstorm/SKILL.md`: section 1 checks the project as `do`'s section 1 does (by reference, not a copy); then the stages in F3. The spec template moves here from `feature.md`, generalized: `Serves:`, `Why`, `Requirements` (ID, requirement, acceptance check, test), `Design`, `Decisions`, `Out of scope`. For a bug fix the Requirements table holds the fixed behavior and the behavior that must not change, and Design holds the root cause with its `file:line`; for perf, the metric, the target and the measurement command; for a refactoring, the pin and the target shape. The builder-check brief is inline (superpowers' `builder-check-prompt.md`, restated for alpha's folder). A spike the user agrees to follows `do`'s Prototype playbook.
- `skills/plan/SKILL.md`: the plan template and self-review from superpowers' writing-plans, with alpha's commit skill instead of `git commit` lines and the spec's test names in each task. Perf tasks are hypotheses, cheapest first, each with its keep rule (`perf.md` step 4); a refactoring's first task is the subtraction commit.
- `skills/execute/SKILL.md`: native mode from superpowers' executing-plans and Subagents mode from its subagent-driven-development, one task at a time, with alpha's Subagents brief from `do`'s section 3. The final review is alpha's principles reviewer, then the fix check, because the merge guard blocks open findings until a fix check closes them (`project-files/hooks/review.py:612-628`) and passes once the last review covers HEAD's tree (`:630-632`).

All three keep `do`'s section 3 rules (questions, evidence, subagents, branch, worktrees, Done) by pointing to `${CLAUDE_PLUGIN_ROOT}/skills/do/SKILL.md`; execute replaces Done's step 4 with its own final review.

**Data shape.**

- Folder `docs/alpha/<features|bug-fixes|refactorings|perf>/<YYYY-MM-DD>-<slug>/`: `research.md`; `specification.md` with `Status: draft` → `approved by the user on <date>`; `plan.md` with `Status: approved by the user on <date>, built native | with subagents`.
- Ledger `.claude/alpha/notes/<slug>/progress.md`, gitignored and the one place under `.claude/alpha/` the path guard lets the agent write (`project-files/hooks/_common.py:532-533`). Line 1: `# Ledger: <plan path>`. Then `Pre-flight: …`, `Task <N>: complete (commits <a>..<b>, tests: <command> → <result>)`, `Task <N>: Ruling: <what> — <why> — <cost if wrong>`, `Final: …`. A ledger whose first line names another plan belongs to that plan.
- States: researching → designing → spec approved → plan approved (with mode) → task N → reviewed → fix-checked → done. The ledger and the Status lines hold where a task is; execute deletes its ledger folder when it finishes.

**What changes in `do`.**

- `feature.md` becomes light: research the code (Investigation 1 to 4), name the data shape, open product areas named with `/alpha:update <area>`, a short design stated in chat (approach, why not the others, what changes for callers), tests first, code, docs, verify, Done. No folder, no approval gate.
- `bug-fix.md`, `refactoring.md`, `perf.md`, `investigation.md`, `prototype.md` keep their steps.
- `session-pickup.md` step 1 also looks for ledgers; with one, the rest goes to `/alpha:execute`.
- `pause.md`: while executing, the resume note names the ledger instead of repeating it.
- `SKILL.md` section 2 says the full track is `/alpha:brainstorm <task>`, and its description and Feature row drop the spec and plan.

**Docs.** `docs/specification.md`: the Commands table gets `brainstorm`, `plan`, `execute`; R8.1 and R8.2 are rewritten and R8.3 to R8.6 added from F1 to F7; the "update, do" section describes both tracks; the layout tree names the four folders. README's "Work in it" and layout table, this repo's CLAUDE.md line on `/alpha:do`, CONTRIBUTING.md's line 7, and `src/alpha/render/docs.py` (the skills line and the Docs line) say the same. Projects pick up the rendered lines with `/alpha:update` after the release.

**Failure paths.** `/alpha:plan` with no approved spec, or `/alpha:execute` with no approved plan, says which file is missing or unapproved and that `/alpha:brainstorm` makes it, and stops. A task type brainstorm doesn't take goes back to `/alpha:do` with that reason. A ledger that names another plan is left alone.

## Decisions

- Two tracks for every task type; the command the user types picks the track, Claude never does (the user, 2026-11-20).
- The full track is three skills, each runnable on its own, so a spec the user wrote can go straight to `/alpha:plan` and a paused build resumes with `/alpha:execute` (the user, 2026-11-20).
- `/alpha:execute` ends with the principles review once; R8.2 still holds for `/alpha:do` (the user, 2026-11-20).
- The full track's folder is named by the playbook (the user, 2026-11-20). The two existing `docs/alpha/features/` folders stay.
- Investigation, Prototype, Pause and Session pickup have one track: an investigation changes nothing, the others are modes, not task types (Claude's call).
- Two approvals, the spec and then the plan with its mode, as superpowers has them (Claude's call).
- No helper scripts: the ledger is written by hand and the Stop hook already blocks failing checks; a tested `alpha plan` CLI can follow if hand-written ledgers drift (Claude's call, `smallest-change`).
- Subagents mode runs one task at a time, as superpowers does; `feature.md`'s side-by-side worktrees and cherry-picks go, since one ledger can't track parallel tasks (Claude's call).
- Subagents run on the chat's model, as `do`'s section 3 says (Claude's call).
- superpowers' finishing-a-development-branch is not ported: CONTRIBUTING.md's Branching, the merge guard and Done already end a branch, and alpha leaves worktree removal to the user (Claude's call).

## Out of scope

- Behavioral tests of the skills with a person answering (superpowers' writing-skills); the tests check the skills' text, as `docs/specification.md`'s Requirements say.
- systematic-debugging's extra techniques and receiving-code-review's procedure.
- Moving the two existing feature folders or this repo's own `.claude/` copies; the release's `alpha update` brings the copies.
- Any change to the principles reviewer, the merge guard or the hooks.
