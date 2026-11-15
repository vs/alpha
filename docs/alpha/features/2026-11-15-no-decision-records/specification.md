# No decision records

Date: 2026-11-15
Status: approved by the user on 2026-11-15, built native in this checkout
Serves: R1, R3 and R5 in docs/specification.md

## Why

The user wants decisions to update the docs instead of piling up as separate records: "replace all the decision records with update of the docs, so there are no distinct decision". A project's docs then say what is true now; git history keeps when and why.

## Requirements

| ID | Requirement | Acceptance check | Test |
|---|---|---|---|
| F1 | A generated project has no decision records and its answers no decisions list. | Given a scenario's answers, when the project is generated, then there is no docs/decisions/ folder, project.json has no `decisions` key, and answers that still hold one are refused with a message saying to remove it. | `tests/integration/test_generate.py::test_no_decision_records_are_written` (integration); `tests/unit/test_answers.py::test_a_decisions_list_is_refused` (unit) |
| F2 | Overrides are listed in CONTRIBUTING.md with their reason. | Given an override that loosens a principle for a component, then CONTRIBUTING.md's Overrides table has a row with the principle, the change, the scope and the reason, principles.toml holds the principle's `override` as "<change> (<scope>): <reason>", and CLAUDE.md marks the principle overridden. | `tests/unit/test_render_docs.py::test_overrides_are_listed_with_their_reason` (unit) |
| F3 | A review finding is accepted by a commit trailer. | Given a branch with an open finding F-abc123, when a commit on the branch carries `Accepts: F-abc123 <reason>`, then the review hook treats the finding as accepted; without the trailer it stays open. | `tests/integration/hooks/test_review.py::test_a_commit_trailer_accepts_a_finding` (integration) |
| F4 | An exception is a row in CONTRIBUTING.md's Exceptions table. | Given a branch that loosens a check in one place, then the diff check fails until CONTRIBUTING.md's Exceptions table has a row naming the path and the check with a reason; loosening a baseline needs the same row; dropping an adoption step needs `--reason`, kept in docs/adoption.md. | `tests/integration/checks/test_diff_checks.py::test_an_exception_needs_a_row_in_contributing` (integration) |
| F5 | Nothing alpha ships writes or reads decision records. | Given the kit's skills, copied project files, hooks, checks, recipes and source, then none tells an agent to write a decision record or reads docs/decisions/, and the principles name the docs instead of a decision log. | `tests/unit/test_skills.py::test_no_kit_file_uses_decision_records` (unit) |
| F6 | `/alpha:fold-decisions` folds an existing project's records into its docs. | Given a project with docs/decisions/, then the skill moves each rule still in force into docs/specification.md, CONTRIBUTING.md, the answers' overrides or the Exceptions table, removes the folder and the answers' decisions list (`alpha answers drop-decisions`), and `alpha update --dry-run` reports nothing to change. | `tests/unit/test_skills.py::test_fold_decisions_routes_every_kind_of_record` (unit) |

## Design

**Answers.** `decisions` leaves the answers model: the interview, extend and grilling stop writing it, and `answers check` refuses it ("decisions is no longer part of the answers; run /alpha:fold-decisions"). Overrides keep their `reason` field.

**Renderers.** No decision records; `records.py`'s numbering, the manifest's records and the commit group for them go. CONTRIBUTING.md gains `## Overrides` (a row per override: principle, change, scope, reason) and `## Exceptions` (path, rule, reason; alpha writes the header, agents add rows, and updates keep them). principles.toml's `override_decision` becomes `override`, the change, scope and reason in one line; CLAUDE.md says "(overridden: see CONTRIBUTING.md, Overrides)".

**Hooks and checks.**

- The session start no longer lists decisions.
- `review.py` reads `Accepts: F-… <reason>` trailers from the branch's commits since its base, and its messages say to add one.
- `user_prompt.py` relays "accept F-…" as an instruction to add the trailer.
- `diff_checks.py` reads the Exceptions table for a check loosened on the branch.
- `alpha baseline` needs an Exceptions row to loosen a baseline.
- `alpha adopt drop` takes `--reason` instead of `--decision`.

**Rules.** A change to what the product does (docs/specification.md) needs the user's yes, which the reviewer checks; a change to the process (CONTRIBUTING.md) is Claude's to make with a reason in the commit. This replaces the product/technical `Kind` of records. The principles "Never weaken a check to pass it" and "Never block on the human" name the Exceptions table and the docs instead of a decision.

**Skills.** The `decision` skill becomes "record a decision in the docs": where each kind goes (product: the spec through `/alpha:extend` or the feature spec; process: CONTRIBUTING.md; a principle change: the answers' overrides; an exception: the Exceptions table; a finding: a commit trailer). Every area skill, extend, grilling, new-project, adopt, the go playbooks, the reviewer agent and the copied skills follow it.

**Folding.** `/alpha:fold-decisions` is a plugin skill for a project that has records: an area record or one whose rule the docs already state is dropped; an override record keeps its reason in the answers; an exception record becomes an Exceptions row; any other rule still in force goes into the doc it governs, then docs/decisions/ and the answers' decisions list go (`alpha answers drop-decisions <target>`, the one CLI step, since the answers refuse the list), followed by `alpha update` and `commit-update`.

**alpha itself.** alpha's 35 records are folded with the skill, by hand, as the last task. mental is re-adopted by the user.

## Plan

1. Answers and rendering: drop `decisions`, the records and their numbering; Overrides and Exceptions tables; `override` (`answers.py`, `records.py`, `principles.py`, `render/*`, `generate.py`, `update.py`, `gitops.py`, their tests). Makes F1 and F2 pass.
2. Hooks and checks: review trailers, the prompt relay, the session start, diff checks, baselines, adopt drop (`project-files/hooks/*`, `project-files/checks/diff_checks.py`, `baseline.py`, `adopt.py`, `cli.py`, their tests). Makes F3 and F4 pass.
3. Skills and principles: the decision skill, every skill that writes or reads decisions, the reviewer agent, the copied skills, the two principles, CLAUDE.md's working rules (`skills/**`, `project-files/**`, `defaults/defaults.toml`, `tests/unit/test_skills.py`). Makes F5 pass.
4. `/alpha:fold-decisions` (`skills/fold-decisions/SKILL.md`, its test). Makes F6 pass.
5. Docs: the design spec, README, CLAUDE.md.
6. alpha itself: fold its records and move its files by hand.

## Decisions

- Decision records go everywhere; a one-off skill folds existing ones (user).
- The docs keep no "Why" for ordinary choices (user); overrides and exceptions keep a reason because the principles require one.
- An accepted finding is a commit trailer (user).
- An exception is a row in CONTRIBUTING.md's Exceptions table; a dropped adoption step keeps its reason in the plan (user).
- The answers' decisions list goes (user).
- Claude's choice: a change to docs/specification.md's product content needs the user's yes, replacing the record `Kind`.
- Claude's choice: folding is a skill, since routing a record's prose into the right doc takes judgment a CLI can't make.

## Out of scope

- Keeping superseded history anywhere but git.
- Migrating projects other than alpha.
