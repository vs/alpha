# alpha rewrite: specification

Date: 2026-11-15
Status: draft, waiting for the user's approval; nothing is built before it
Research: [research.md](research.md). Plan: [plan.md](plan.md).

## Why

alpha grew into 42,000 lines that set up the whole product up front, review in cycles, spread docs over `docs/`, and keep file hashes in a committed file. The user wants a new product built to their requirements: alpha sets up the development process only, puts its docs in one place, reviews once before main without looping, and can be switched off or removed cleanly. The current code is a source of knowledge, not a structure to keep.

## Commands

| Command | Form | What it does |
|---|---|---|
| `install` | skill | Puts alpha into a folder: a new project in an empty folder, an adoption in an existing repo, or the hooks back on where they were switched off. |
| `extend` | skill | Applies a change the user describes to an installed project: a component, an answer of an install area. |
| `specify` | skill | Settles one or more product areas the user names, writing their docs into `docs/alpha/`. |
| `do` | skill | Works a task by a playbook; a feature goes through research, brainstorming, a spec and a plan. |
| `update` | skill and CLI | Brings alpha's files in line with the answers and the installed kit; the CLI merges, the skill resolves conflicts. |
| `uninstall` | skill and CLI | Removes alpha's hooks; deletes no file, commits nothing. |
| `purge` | skill and CLI | Uninstalls, deletes alpha's files, and commits the removal as one commit. |

## Requirements

Each ID starts with the number of the user's requirement it serves. Test names are the ones the plan writes; a test that proves an acceptance check names its ID.

| ID | Requirement | Acceptance check | Test |
|---|---|---|---|
| R1.1 | `install` in an empty folder sets up a new project from the install answers. | Given an empty folder and finished install answers, when `alpha apply`, `alpha bootstrap` and `alpha commit` run, then the folder holds the files of the Layout section and no app code, every component check and `mise run ci` pass, and the tree is clean on `main`. | `tests/integration/test_apply.py::test_R1_1_a_new_project_gets_the_layout` (integration); `tests/end-to-end/test_install_slow.py::test_R1_1_empty_folder_becomes_a_checked_project` (end-to-end) |
| R1.2 | `install` tells the folder's state apart and takes the matching path. | Given an empty folder, a git repo with commits, a non-empty folder that isn't a git repo, an installed project with its hooks on, and one with its hooks off, when `alpha status <folder>` runs, then it prints `empty`, `existing`, `not-a-repo`, `installed` and `hooks-off`, and the install skill names the path it takes for each. | `tests/integration/test_status.py::test_R1_2_each_folder_state_is_told_apart` (integration); `tests/unit/test_skills.py::test_R1_2_install_routes_each_state` (unit) |
| R1.3 | `install` in an existing repo runs today's adoption, with the compliance plan in `docs/alpha/`. | Given a clean repo with legacy lint findings and finished adoption answers, when `alpha apply`, `alpha bootstrap --capture-baselines` and `alpha commit` run, then alpha's files are committed on `alpha/adopt`, the existing findings pass as baselined, a new finding fails its check, and the plan is `docs/alpha/adoption.md`. | `tests/integration/test_adopt.py::test_R1_3_adoption_installs_on_its_branch` (integration); `tests/end-to-end/test_adopt_slow.py::test_R1_3_legacy_findings_pass_and_new_ones_fail` (end-to-end) |
| R1.4 | `install` where alpha is installed with its hooks off turns them back on without asking. | Given an installed project after `alpha uninstall`, when `alpha hooks on` runs, then `.claude/settings.json` has every alpha hook entry again with its other entries unchanged, `core.hooksPath` is alpha's (alpha mode), and the install skill asks no question on this path. | `tests/integration/test_uninstall.py::test_R1_4_hooks_on_restores_what_uninstall_removed` (integration); `tests/unit/test_skills.py::test_R1_4_install_turns_hooks_on_without_asking` (unit) |
| R2.1 | `uninstall` removes alpha's hook entries and its `core.hooksPath`, and nothing else. | Given an installed project whose `settings.json` also holds the user's own hook and permissions, when `alpha uninstall` runs, then no hook command names `.claude/alpha/hooks/`, the user's hook and every permission stay, `core.hooksPath` is unset, no file is deleted, and HEAD is unchanged. | `tests/integration/test_uninstall.py::test_R2_1_uninstall_removes_only_the_hook_wiring` (integration) |
| R2.2 | In a repo whose hook manager runs git's hooks, `uninstall` leaves `core.hooksPath` alone. | Given an adopted repo with `git_hooks = chain` and `core.hooksPath = .husky`, when `alpha uninstall` runs, then `core.hooksPath` is still `.husky` and the output names the hook-manager line that still calls alpha's `commit-msg`. | `tests/integration/test_uninstall.py::test_R2_2_a_chained_repo_keeps_its_hooks_path` (integration) |
| R2.3 | The guards block every habitual way to remove the hooks other than `uninstall`. | Given an installed project, then an Edit or Write that removes or changes an alpha hook entry in `settings.json`, an Edit or Write under `.claude/alpha/`, a Bash write (redirect, `cp`, `mv`, `rm`, `tee`, `sed -i`, …) to either, and `git config core.hooksPath <other>` or `--unset` are each blocked with a message naming `/alpha:uninstall`; an Edit of `settings.json` that only adds a permission passes. | `tests/integration/hooks/test_guard_paths.py::test_R2_3_edits_to_the_hook_wiring_are_blocked` (integration); `tests/integration/hooks/test_guard_bash.py::test_R2_3_shell_ways_to_remove_the_hooks_are_blocked` (integration) |
| R2.4 | `uninstall` works despite the guards. | Given an installed project with its hooks on, when the command guard sees `<plugin>/bin/alpha uninstall .`, then it passes, and the command removes the hooks. | `tests/integration/hooks/test_guard_bash.py::test_R2_4_alpha_uninstall_passes_the_guard` (integration) |
| R3.1 | `purge` uninstalls, deletes alpha's files even when edited, and commits the removal as one commit. | Given an installed project with a hand edit in `.claude/skills/commit/SKILL.md` and in `docs/alpha/specification.md`, when `alpha purge` runs, then `.claude/alpha/`, alpha's agents and skills, `docs/alpha/` and alpha's `settings.json` entries are gone, the hooks are uninstalled, and HEAD is one new commit holding exactly those removals and edits. | `tests/integration/test_purge.py::test_R3_1_purge_removes_alpha_in_one_commit` (integration) |
| R3.2 | `purge` removes from `CLAUDE.md` only the lines that point at alpha's hooks, docs, skills and agents. | Given a generated `CLAUDE.md` with a line the user added, when `alpha purge` runs, then no line names `.claude/alpha/`, `docs/alpha/`, an `/alpha:` command or a removed skill or agent, the user's line and the principles, commands and rules stay, and no heading is left without content. | `tests/unit/test_purge.py::test_R3_2_only_alphas_lines_leave_claude_md` (unit) |
| R3.3 | After `purge` the project still builds and tests. | Given a generated project with two components, when `alpha purge` runs, then no kept file (tool configs, `mise.toml`, CI workflows, `.gitignore`, `CONTRIBUTING.md`, `README.md`, `LICENSE`, `CLAUDE.md`, `settings.json`) names a deleted path, and every component check and `mise run ci` pass. | `tests/unit/test_purge.py::test_R3_3_no_kept_file_names_a_deleted_path` (unit); `tests/end-to-end/test_purge_slow.py::test_R3_3_a_purged_project_builds_and_tests` (end-to-end) |
| R3.4 | `purge` commits only alpha's removals. | Given an installed project with an uncommitted change to `README.md`, when `alpha purge` runs, then the change to `README.md` is still uncommitted and the purge commit doesn't hold it. | `tests/integration/test_purge.py::test_R3_4_purge_commits_only_alphas_paths` (integration) |
| R4.1 | `extend` applies a described change to an installed project and keeps the user's edits. | Given a generated project with a hand edit in `CLAUDE.md`, when a component is added to the answers and `alpha update`, `alpha bootstrap --component` and `alpha commit` run, then the component is set up, the edit survives, and a second `alpha update --dry-run` prints nothing to change. | `tests/integration/test_update.py::test_R4_1_a_new_component_merges_and_keeps_an_edit` (integration) |
| R5.1 | The answers of an install hold only the install areas; product areas stay open. | Given answers with the ten install areas done and every product area open, when `alpha answers check` runs, then it prints ok; identity holds no target users or requirements and security no auth; an install area marked open is refused with a message naming it. | `tests/unit/test_answers.py::test_R5_1_install_needs_only_the_install_areas` (unit); `tests/unit/test_answers.py::test_R5_1_an_install_area_cant_stay_open` (unit) |
| R5.2 | The install interview runs only the install areas and may ask what the project is about in one line. | Given the install skill, then it reads the area guides of exactly the install areas, and none of the product areas. | `tests/unit/test_skills.py::test_R5_2_install_reads_only_install_area_guides` (unit) |
| R5.3 | A principle a product area settles stays off while that area is open. | Given a component with a UI and ui and accessibility open, then `visual-system` and `accessibility` are inactive in `docs/alpha/principles.toml`; likewise each principle with `settled_by`. | `tests/unit/test_principles.py::test_R5_3_open_areas_keep_their_principles_off` (unit) |
| R6.1 | alpha writes the process into `CONTRIBUTING.md`, every other doc under `docs/alpha/`, and nothing else into `docs/`. | Given a generated project, then `CONTRIBUTING.md` holds the components, checks, testing, documentation, branching, build, CI, hosting, releases, secrets, protected paths, overrides and exceptions; `docs/alpha/` holds `principles.toml`, `dependencies.md` and `specification.md`; no other file under `docs/` was written by alpha. | `tests/integration/test_apply.py::test_R6_1_docs_go_to_contributing_and_docs_alpha` (integration) |
| R6.2 | Where the project already has a doc for an area, alpha's file refers to it. | Given answers that name `docs/architecture.md` as the existing doc for architecture, when architecture is settled, then `docs/alpha/specification.md`'s Architecture section links to it instead of repeating it. | `tests/unit/test_render_docs.py::test_R6_2_an_existing_doc_is_referred_to` (unit) |
| R6.3 | In an existing repo alpha never overwrites `CLAUDE.md`, `README.md` or `LICENSE`. | Given a repo with its own three files, when `alpha apply` runs, then each is unchanged on disk and alpha's version is a proposal for a hand merge. | `tests/integration/test_adopt.py::test_R6_3_root_files_get_proposals` (integration) |
| R6.4 | alpha generates `CLAUDE.md`, `README.md` and `LICENSE` at the root. | Given a generated project, then `README.md` holds the name, the one-line purpose and each component's setup, test and run commands, `LICENSE` holds the chosen license, and `CLAUDE.md` exists. | `tests/unit/test_render_docs.py::test_R6_4_root_docs_are_generated` (unit) |
| R7.1 | `specify` settles the product areas the user names and closes them. | Given a project with ui and performance open, when both are answered, marked done and `alpha update` runs, then `docs/alpha/specification.md` has their sections and no longer lists them as open, and their principles are active. | `tests/integration/test_update.py::test_R7_1_settling_areas_writes_their_docs` (integration) |
| R7.2 | Only `specify` works on the product layer, and only when the user asks. | Given the kit's skills, then only `specify` reads a product area guide, and `do` and `extend` point to `/alpha:specify` instead of settling one. | `tests/unit/test_skills.py::test_R7_2_only_specify_settles_product_areas` (unit) |
| R8.1 | `do` works a task by a playbook; a feature goes through research, brainstorming, a spec and a plan in its own folder. | Given the do skill, then its feature playbook runs deep research into how other projects build the feature, brainstorms with the user one question at a time with two or three approaches, and writes `research.md`, `specification.md` and `plan.md` into `docs/alpha/features/<date>-<feature>/`, the spec naming a test per acceptance check and approved before code. | `tests/unit/test_do_skill.py::test_R8_1_a_feature_gets_research_spec_and_plan` (unit) |
| R8.2 | `do` runs no whole-branch review. | Given the do skill and its playbooks, then none asks for a review of the whole branch; the principles review happens at merge. | `tests/unit/test_do_skill.py::test_R8_2_do_runs_no_whole_branch_review` (unit) |
| R9.1 | The principles review never runs at Stop or after a task. | Given a project with 2,000 unreviewed lines on a branch, when the Stop hook runs, then it doesn't ask for a review. | `tests/integration/hooks/test_stop_checks.py::test_R9_1_stop_never_asks_for_a_review` (integration) |
| R9.2 | Nothing reaches main before its tree is reviewed with no open findings. | Given a branch whose HEAD tree has no note, when Claude runs `git push origin main` or `gh pr merge`, then the command guard blocks it and says to run the principles-reviewer; given a note on HEAD's tree with no open findings and a recorded test pass, it passes. | `tests/integration/hooks/test_review.py::test_R9_2_merge_waits_for_a_review_of_the_head_tree` (integration) |
| R9.3 | A review never loops: after a review with findings, the next one only checks those findings. | Given a reviewed tree whose note holds findings F-1 and F-2, when commits fix F-1 and accept F-2 with an `Accepts:` trailer, then the next brief is a fix check listing F-1 and F-2 only, its record can't add a finding, and once both are resolved the merge passes. | `tests/integration/hooks/test_review.py::test_R9_3_a_fix_check_adds_no_findings` (integration) |
| R10.1 | A review's result is a git note on the reviewed tree, under its own notes ref, recorded from any worktree; nothing else writes it. | Given the reviewer's json for a tree a brief handed out, when the SubagentStop hook records it, then `git notes --ref=alpha-review show <tree>` holds the result, also when the brief ran in a linked worktree and the hook in the main checkout; a tree no brief handed out is refused; Claude's `git notes --ref=alpha-review add` is blocked. | `tests/integration/hooks/test_review_record.py::test_R10_1_a_review_is_a_note_on_its_tree` (integration); `tests/integration/hooks/test_guard_bash.py::test_R10_1_writing_review_notes_is_blocked` (integration) |
| R10.2 | The last reviewed tree is found by walking the history; with none, the branch since main is reviewed. | Given commits A–B–C after main, with a note on B's tree only, then the brief's base is B's tree; with no note, the base is the tree of the merge base with main. | `tests/integration/hooks/test_review.py::test_R10_2_the_last_reviewed_tree_is_found_in_history` (integration) |
| R10.3 | A review covers only the files changed since the last reviewed tree. | Given a note on B's tree and C changing one file, then the brief lists that one file and its diff, and no file B already had. | `tests/integration/hooks/test_review.py::test_R10_3_the_brief_holds_only_files_changed_since` (integration) |
| R10.4 | The review notes stay local. | Given an installed project, then nothing alpha writes configures notes to be pushed, and Claude's `git push origin refs/notes/alpha-review` is blocked. | `tests/integration/hooks/test_guard_bash.py::test_R10_4_pushing_review_notes_is_blocked` (integration) |
| R11.1 | `update` merges changed answers against alpha's last render, kept as a git commit, not in project.json. | Given a generated project, then `refs/alpha/rendered` points at a commit whose tree is alpha's render; after an answer changes, `alpha update` merges with that tree as the base; with the ref deleted, every file that differs from the new render becomes a two-sided proposal. | `tests/integration/test_update.py::test_R11_1_the_base_is_alphas_last_render` (integration); `tests/integration/test_update.py::test_R11_1_without_the_base_differences_become_proposals` (integration) |
| R11.2 | `update` brings a project to a newer kit the same way. | Given a generated project with a hand edit in `CONTRIBUTING.md`, when the kit's renderer changes another part of `CONTRIBUTING.md` and `alpha update` runs, then the file holds both the kit's change and the hand edit, and a changed copied hook is replaced. | `tests/integration/test_update.py::test_R11_2_a_kit_change_merges_into_an_edited_file` (integration) |
| R11.3 | The update skill resolves the conflicts the CLI leaves. | Given the update skill, then it runs `alpha update`, merges each proposal by hand keeping both sides, and commits with `alpha commit`. | `tests/unit/test_skills.py::test_R11_3_update_skill_merges_proposals` (unit) |
| R12.1 | Setup data stays: Python, TypeScript and Rust recipes; drafted recipes proven by `recipe try` and saved by `recipe save`; the registry with pins and `registry stale`; the user's defaults layer with "make this the default?". | Given a stack the kit has no recipe for, when a drafted recipe is saved, then `answers check` refuses it until `recipe try` proves it; `registry stale` lists a tool reviewed 181 days ago; `defaults set` puts a value on top of the kit's. | `tests/integration/test_recipes.py::test_R12_1_a_drafted_recipe_needs_a_proof` (integration); `tests/integration/test_registry.py::test_R12_1_stale_tools_are_listed` (integration); `tests/integration/test_defaults.py::test_R12_1_a_user_default_wins` (integration) |
| R12.2 | The checks stay: secrets, vulnerabilities, spelling, Markdown, links, agent config, weekly tool freshness, immutable migrations and SQL lint, review dates, palette, diff coverage, and each changed component's full suite before main with a remembered pass. | Given a generated project, then `mise.toml` has a task per check in the Checks section, each fails on its seeded violation, and the merge guard blocks until `stop_checks.py tests` passed on the current files. | `tests/integration/test_repo_checks.py::test_R12_2_every_check_is_wired` (integration); `tests/end-to-end/test_install_slow.py::test_R12_2_each_check_fails_on_its_seed` (end-to-end); `tests/integration/hooks/test_stop_checks.py::test_R12_2_main_waits_for_a_test_pass` (integration) |
| R12.3 | Adopted repos keep baselines with the ratchet and the compliance plan. | Given an adopted repo with a lint baseline, then a fixed finding tightens the baseline, a new finding fails, and `adopt done` marks a step only when its acceptance holds. | `tests/integration/test_baseline.py::test_R12_3_the_ratchet_only_tightens` (integration); `tests/integration/test_adopt.py::test_R12_3_a_step_is_done_only_when_its_acceptance_holds` (integration) |
| R12.4 | CI generation and per-stack permissions stay. | Given a project with CI on GitHub Actions, then `.github/workflows/ci.yml`, `scheduled.yml` and `dependabot.yml` are written with actions pinned by SHA, and `settings.json` allows each component's stack commands. | `tests/unit/test_render_ci.py::test_R12_4_ci_runs_each_components_checks` (unit); `tests/unit/test_render_settings.py::test_R12_4_each_stack_gets_its_permissions` (unit) |
| R12.5 | The agents and skills stay: `principles-reviewer`, `committer`, `/commit`, `review-change`, `/audit`, `decision`. | Given a generated project, then `.claude/agents/` holds the two agents and `.claude/skills/` the four skills, and none of them names a decision record. | `tests/integration/test_apply.py::test_R12_5_projects_get_the_agents_and_skills` (integration) |
| R12.6 | The hooks stay: command guard, file guard, Stop checks, post-edit checks, session and subagent context, the `commit-msg` git hook, `untested` notes, and the review record. | Given a generated project, then `settings.json` wires SessionStart, SubagentStart, PreToolUse (Bash; Edit, Write, MultiEdit), PostToolUse, Stop, SubagentStop and the reviewer's SubagentStop, and `untested.py` records a reason the Stop check accepts while the file is unchanged. | `tests/unit/test_render_settings.py::test_R12_6_settings_wire_each_hook` (unit); `tests/integration/hooks/test_stop_checks.py::test_R12_6_an_untested_note_holds_until_the_file_changes` (integration) |
| R13.1 | Fast checks run where they do today, and bind Claude only. | Given an edit of a source file, then post-edit formats and lints it; given changed source at Stop, then the Stop hook runs the type check, the structure check and the fast repository checks, and no test suite. | `tests/integration/hooks/test_post_edit.py::test_R13_1_an_edit_is_formatted_and_linted` (integration); `tests/integration/hooks/test_stop_checks.py::test_R13_1_stop_runs_types_structure_and_fast_checks` (integration) |
| R13.2 | The only git hook is `commit-msg`. | Given a generated project, then `.claude/alpha/githooks/` holds only `commit-msg`, and it rejects a message that breaks the convention for any committer. | `tests/integration/test_apply.py::test_R13_2_commit_msg_is_the_only_git_hook` (integration); `tests/integration/hooks/test_commit_msg.py::test_R13_2_a_bad_message_is_rejected` (integration) |
| R14.1 | The mutation-testing gate, `/debt` with the `shortcut:` ledger check, and the interview evals are gone. | Given the kit's tree, then no file names `cargo-mutants`, `mutants`, `check:shortcuts`, `/debt` or `alpha-evals`, and `src/alpha_evals`, `bin/alpha-evals` and `evals/` don't exist. | `tests/unit/test_kit.py::test_R14_1_dropped_features_are_gone` (unit) |
| R15.1 | There are no decision records in any form. | Given the kit's skills, copied files, renderers and CLI, then none writes or reads `docs/decisions/` or a decision record, and the answers refuse a `decisions` key. | `tests/unit/test_kit.py::test_R15_1_no_decision_records` (unit) |
| R16.1 | No committed file alpha writes holds file hashes or a tree snapshot. | Given a generated, updated and adopted project, then no file in the tree alpha wrote, `project.json` included, holds a `sha256:` digest or a list of the project's files with hashes; alpha's base lives in `refs/alpha/rendered`. | `tests/integration/test_apply.py::test_R16_1_no_committed_file_holds_file_hashes` (integration) |

## Design

### Layout of a project

```text
CLAUDE.md                 alpha's (proposed, not written, in an existing repo)
README.md                 alpha's (same)
LICENSE                   alpha's (same)
CONTRIBUTING.md           the process: everything install sets up
CHANGELOG.md              when the releases area keeps one
mise.toml                 the repository checks' tools and tasks
_typos.toml, .rumdl.toml, lychee.toml, .betterleaks.toml
.gitignore
.github/                  ci, scheduled, dependabot, jactionlint
docs/alpha/
  principles.toml         the one file the hooks and reviewer read
  dependencies.md         the dependency log
  specification.md        the product: purpose, open areas, settled areas
  glossary.md             once architecture is settled with a glossary
  design-language.md      once the design language is settled
  adoption.md             an adopted repo's compliance plan
  features/<date>-<feature>/  research.md, specification.md, plan.md
.claude/
  settings.json           permissions and alpha's hook entries
  agents/                 principles-reviewer.md, committer.md
  skills/                 commit, decision, review-change, audit
  alpha/
    project.json          the answers and the install record
    hooks/, checks/, githooks/commit-msg
    baselines/            adopted repos only
    state/                gitignored
<component>/              manifest, configs, a setup test
```

`docs/alpha/specification.md` at install holds the value proposition and the list of open product areas, each with the `/alpha:specify` request that settles it. `specify` adds each settled area's section; an area the project already documents gets a link to that doc (R6.2) instead of a copy, from `documentation.existing`, a map of area to path that the documentation area fills in an existing repo.

### Answers

`.claude/alpha/project.json`, parsed at the boundary into frozen dataclasses as today, with a message per error naming the field and the fix.

- **Install areas:** `identity` (name, slug, one-line purpose, license or license file, copyright holder), `components`, `testing` (levels, diff coverage, exhaustive), `documentation` (where user docs live, docs map, existing docs per area), `build`, `security` (secret store, extra protected paths), `dependencies`, `releases`, `git`, `agent_workflow` (extra risk paths only).
- **Product areas** (start `open`; only `specify` settles them): `requirements` (target users, requirements with acceptance checks, domain jargon), `architecture` (with the glossary), `errors`, `design_language`, `ui`, `accessibility`, `observability`, `data`, `performance`, `auth`.
- Gone: `manifest` (hashes, answers copy, kit source path), `decisions`, `review_mode`, `max_lines`, `max_files`, `testing.run`, `testing.mutants`, `identity.target_users`, `identity.requirements`, `security.auth`.
- New: `installed` = `{kit_version, mode: "new" | "adopted", on: <date>, components: {<name>: <date added>}}`, written by `alpha apply`. The component dates keep the dependency log's entries stable across updates.
- A principle with `settled_by = "<area>"` stays inactive while that area is open, as today.

### Writing files: one pipeline

`render(answers, kit) → {path: text}` is pure: principles, docs, settings, tooling, CI, component templates, and the copied hooks, checks, agents and skills. `alpha apply` and `alpha update` then:

1. Read the base: the tree of `refs/alpha/rendered`, or nothing.
2. For each path, merge three ways (base, disk, new render) with `git merge-file`, as `merge.py` does today: `new`, `change`, `merge`, `conflict` (a proposal in `.claude/alpha/state/update/<path>`), `stale`, `skipped`. Without a base, a file that exists and differs is a two-sided proposal; `.gitignore` and `settings.json` merge mechanically (lines; JSON keys), as adoption does today.
3. Write, then store the new render as a commit (temporary index, `write-tree`, `commit-tree`, parent the previous one) and point `refs/alpha/rendered` at it. A dry run writes nothing.

`alpha commit <project>` commits alpha's writes in today's groups (docs, chore, tooling, one per component or workspace, ci, dependabot), replacing `commit-skeleton` and `commit-update`. A kit upgrade is the same operation: the base is what the older kit rendered, read from the ref, so no older kit runs.

The ref is local and repo-wide; another clone renders with no base and gets proposals (decided with the user). Worktrees share it.

### install

The skill runs `alpha status <folder>` and follows it:

- `empty`: today's new-project, limited to the install areas: defaults, the interview (one question at a time, a recommendation each, "make this the default for future projects?" on an override), a summary, `alpha apply`, `alpha bootstrap`, `alpha commit` on `main` (git init when needed), "save this drafted recipe?".
- `existing` (a git repo with at least one commit, a clean tree, HEAD on a branch): today's adoption, unchanged but for its interview scope and the plan's path. A repo with docs and no code yet is `existing` too; its components get skeletons after one question, as today.
- `not-a-repo` (files but no git repository): refused with "Run git init and commit the files, then install again."
- `installed`: says so and points to `/alpha:extend`, `/alpha:specify` and `/alpha:update`.
- `hooks-off` (installed, and `settings.json` lacks alpha's hook entries or, in alpha mode, `core.hooksPath` isn't alpha's): runs `alpha hooks on` and reports what it restored, asking nothing. It commits nothing, as `uninstall` doesn't.

The area guides become files under `skills/install/areas/` (install areas) and `skills/specify/areas/` (product areas), read by those skills, instead of 18 plugin skills. `grilling` and `stack-recipe` stay skills.

### uninstall, hooks on

- `alpha uninstall <project>`: removes from `settings.json` every hook entry whose command names `.claude/alpha/hooks/` (an emptied matcher group and an emptied event go too) and unsets `core.hooksPath` when it is `.claude/alpha/githooks`. In chain mode it prints the hook-manager line that still calls alpha's `commit-msg`. No file is deleted, nothing is committed.
- `alpha hooks on <project>`: puts alpha's hook entries back from the render (merged into the file as it is) and, in alpha mode, sets `core.hooksPath`.
- The guards (R2.3) protect the wiring. The file guard blocks an Edit or Write under `.claude/alpha/` and one to `settings.json` whose parsed alpha hook entries differ before and after. The command guard blocks Bash writes to those paths and changes to `core.hooksPath`. Each message names `/alpha:uninstall`. `alpha uninstall` itself is a CLI the guards don't parse as a write (habits, not evasion, as PR #46 settled).
- The uninstall and purge skills are user-invocable only (`disable-model-invocation`), and CLAUDE.md says Claude runs them only when the user asks (decided with the user).

### purge

`alpha purge <project>`: refuses during an unfinished update; runs uninstall; then:

- Deletes `.claude/alpha/`, alpha's agents and skills under `.claude/` (the ones `render` copies), and `docs/alpha/`.
- Edits the kept files so none names a deleted path (R3.3): drops `settings.json` hook entries and permission rules naming alpha's files (stack permissions stay; an emptied file is deleted); drops `mise.toml` tasks whose `run` names `.claude/alpha/` and their names in `depends`; drops CI steps that run them; unwraps a component command that runs through `ratchet.py` back to the plain command; drops `.gitignore` lines naming `.claude/alpha/`; drops each `CLAUDE.md` line naming `.claude/alpha/`, `docs/alpha/`, an `/alpha:` command or a removed skill or agent, then a heading left empty; drops the chained line from a hook-manager file.
- Deletes `refs/alpha/rendered` and `refs/notes/alpha-review`.
- Stages exactly those paths and commits `chore: Remove alpha` with the session's trailers. Uncommitted changes elsewhere stay uncommitted.

The removers are line-based on the layout `render` writes, so they are pure functions with unit tests.

### extend, specify, do

- **extend** keeps today's flow for the install areas and components: re-ask only what the change affects, `answers write`, `alpha update --dry-run`, confirm, `alpha update`, merge proposals, `alpha bootstrap --component`, `alpha commit`. A product area request points to `/alpha:specify`.
- **specify** takes the areas the user names (one or several). For each: research what the code and docs already imply and the kit default, lay out two or three options, settle the questions with `grilling`, save with `answers write`, mark the area `done`. Then `alpha update`, verify the sections and principles, `alpha commit`.
- **do** keeps the pstack playbooks (investigation, feature, bug fix, refactoring, perf, prototype, session pickup, pause; the Specify playbook leaves, `specify` replaces it). The feature playbook:
  1. Research the code the feature touches.
  2. Deep research: subagents look at how other projects build the feature (libraries, products, write-ups) and write `research.md` with sources.
  3. Brainstorm with the user as superpowers does: one question at a time, two or three approaches with trade-offs and a recommendation, the design shown in sections the user confirms.
  4. Write `specification.md` (requirements, acceptance checks, a test per check, design, decisions, out of scope) and `plan.md` (ordered tasks, files, tests).
  5. The user approves the spec and picks native or subagents.
  6. Build tests first, verify, finish with the definition of done.
  An open product area the feature needs is named to the user with `/alpha:specify`; the feature's own choices stay in its spec. No whole-branch review: per-task reviews in subagent mode stay (the user's choice of mode), and the principles review runs at merge.

### Review

- **When:** only at the merge gate. The command guard runs it on `git push` to a main branch and `gh pr merge` whose branch is checked out here. The gate also needs a remembered test pass on the current files (`stop_checks.py tests`). Stop never asks for a review.
- **Where:** a note per reviewed tree under `refs/notes/alpha-review`, holding `{"kind": "review" | "fix-check", "base": <tree>, "findings": [{id, principle, file, line, problem, fix, status}]}`, status `open`, `fixed` or `accepted`.
- **Base:** walk `git rev-list HEAD` back to and including the merge base with main; the first commit whose tree has a note gives the last review. None: the merge base's tree.
- **Brief** (`review.py brief`): with no open findings in the last note, a review of the files changed between the base and `HEAD^{tree}` (principles, stack rules, exceptions, expected load, untested notes, changed visuals, the diff). With open findings, a fix check: those findings, the commits since with their `Accepts:` trailers, and the diff for context, no other files. The brief records the tree it hands out in `<git common dir>/alpha/briefs.json`, so any worktree's hook can check it.
- **Record** (`review_record.py`, SubagentStop of `principles-reviewer`): parses the json, refuses a tree no brief handed out, writes the note. A fix check's record may only set the status of findings it was given. Hand-backs are read from the transcript, as today.
- **Accepting:** a finding is accepted by an `Accepts: F-xxxxxx <reason>` trailer, which the fix check judges; on a risk path (`review.risk_paths` plus `agent_workflow.extra_risk_paths`) the reason must quote the user's agreement. `user_prompt.py` goes.
- **Guarded:** Claude's `git notes` commands on `alpha-review`, `git update-ref refs/notes/alpha-review` and a push of that ref are blocked.

What a fix check doesn't see is new work slipped into fix commits. That's the price of never looping, and the next review after a clean note covers anything changed later.

### Hooks and checks

- **Command guard**, trimmed: `--no-verify` (and `commit -n`); changes to `core.hooksPath`; writes to the review notes ref and pushing it; a plain `--force` push and any rewrite of main (a lease push to main, amending a commit already on main); the merge gate; Bash writes to protected paths, `.claude/alpha/` and `settings.json`; the reviewer runs read-only. Gone: `git add -A`/`.`, `commit -a`, `reset --hard`, `checkout .`/`restore .`, `stash`, `clean -x`.
- **File guard:** protected paths, `.claude/alpha/`, the hook wiring in `settings.json`, the weakening patterns (skip markers, ignore comments, loosened strictness) unless an Exceptions row names the file, and an "ask" for `docs/alpha/principles.toml`.
- **Post-edit:** `format_file` and `lint_file` per component, as today.
- **Stop:** secrets in added lines, source changed without tests (unless an `untested` note holds), mapped docs not updated, a lockfile change without a `docs/alpha/dependencies.md` entry, an edited migration that existed before the session, the type check and structure check of each changed component, the `stop = true` repository checks; cached per tree and command; three blocks then a message. No review, no test suite.
- **SubagentStop:** the same checks on the subagent's own files.
- **Session and subagent context:** where the docs are, exceptions, overrides, the code-writing principles, and a warning when `core.hooksPath` or the principles file is broken.
- **Git hook:** `commit-msg` only.
- **Untested notes:** `python3 .claude/alpha/hooks/untested.py "<why>" <path>...`, kept in state with each file's blob until it changes.
- **Repository checks:** as today without `shortcuts`; `palette` only once the design language is settled with `enforce`; migrations checks only once data is settled with migration paths.
- Hooks require Python 3.11 at runtime (the kit does), so `tomllib` imports move to the top and the three `PLC0415` Exceptions rows go; an older `python3` still gets the guard message, printed by a tiny 3.9-safe entry check.

### CLI

`bin/alpha` subcommands:

- For users: `update [--dry-run]`, `uninstall`, `purge`, `version`.
- Helpers the skills call: `status`, `apply [--dry-run]`, `bootstrap [--component …] [--capture-baselines]`, `commit [--trailer …]`, `hooks on`, `answers check|write`, `defaults show|set`, `recipe list|check|try|save`, `registry list|show|stale`, `baseline show|capture|tighten`, `adopt survey|gaps|next|start|done|drop`.
- Gone: `generate`, `commit-skeleton`, `commit-update`, `adopt apply` (all `apply` and `commit` now), `answers drop-decisions`.

### alpha's own source

```text
src/alpha/
  cli.py            argparse and exit codes only
  model.py          the answers dataclasses
  answers.py        parse and write project.json
  kit.py            defaults, user layer, registry, recipes (loading)
  recipes.py        recipe model, templates, drafted recipes
  principles.py     the principles table
  render/           one module per output: principles, claude_md, contributing,
                    readme, specification, settings, gitignore, tooling, ci,
                    components; render/__init__.py assembles the full render
  apply.py          plan, merge, write, the base ref
  merge.py          three-way merge, line and JSON unions
  git.py            the git wrapper, commit groups, hooksPath
  status.py         the folder's state
  hooks_wiring.py   uninstall, hooks on
  purge.py          the removers and purge
  adopt.py          survey, plan steps
  baseline.py       baselines
  bootstrap.py      toolchains, checks, baseline capture
project-files/hooks/  _common.py, guard_bash.py, guard_paths.py, post_edit.py,
                      stop_checks.py, context.py (session and subagent start),
                      review.py, review_record.py, untested.py, commit_msg.py
project-files/checks/ secret_scan.py, diff_checks.py, ratchet.py, review_dates.py,
                      palette.py
skills/             install, extend, specify, do, update, uninstall, purge,
                    grilling, stack-recipe
```

## Decisions

- `update` stays, with alpha's last render as a local git commit under `refs/alpha/rendered` as the base; no answers copy in project.json and no running an older kit (user).
- uninstall and purge aren't guarded against Claude; the skills are user-invocable only and CLAUDE.md forbids running them unasked (user).
- The review findings are the only blocker after a review, and a fix check looks only at them (user, earlier on 2026-11-15).
- Claude's choice: post-edit runs format and lint only and the type check stays at Stop. Requirement 13 says "type-check after each edit" but also "where they do today", and today the type check runs at Stop; a whole-project type check per edit would be slow. Revisit if the user wants it per edit.
- Claude's choice: the command guard's short list is the one in Hooks and checks; the shared-work guards (`add -A`, `commit -a`, `reset --hard`, `stash`, `checkout .`, `clean -x`) go, and CLAUDE.md's working rule to stage by path stays.
- Claude's choice: `CHANGELOG.md` stays at the root, where release tooling and readers expect it; under `docs/alpha/` a purge would delete the project's changelog.
- Claude's choice: alpha no longer creates a user-docs folder (`docs/guide/`); the documentation area records the path and the docs map uses it.
- Claude's choice: a non-empty folder that is a git repo goes through adoption, docs-only repos included; one that isn't a git repo is refused with how to proceed.
- Claude's choice: `install` on the hooks-off path and `uninstall` commit nothing, so a re-enable after an uncommitted uninstall leaves no diff.
- Claude's choice: purge also removes alpha's lines from kept files (mise tasks, CI steps, `.gitignore`, a chained hook line, `CLAUDE.md`) so the project builds and tests without alpha; stack permissions in `settings.json` stay as scaffolding.
- Claude's choice: `agent_workflow` keeps only the extra risk paths; review mode and thresholds lose their job when the review runs only at merge.
- Claude's choice: a risk-path finding is accepted by a trailer quoting the user's agreement, which the fix check judges; `user_prompt.py` goes.
- Claude's choice: `do` never closes a product area; it names `/alpha:specify` for one the feature needs and keeps the feature's own choices in its spec.
- Claude's choice: area guides become files read by `install` and `specify`, not 18 plugin skills; `fold-decisions` and `answers drop-decisions` go with the old projects' migration.
- Claude's choice: the requirements and target users, and auth, become product areas of their own (`requirements`, `auth`) instead of empty fields of identity and security.
- Claude's choice: hooks require Python 3.11, dropping the 3.9 parse constraint and its three Exceptions rows.

## Out of scope

- Migrating projects set up by an older alpha automatically; they follow the steps below by hand.
- Pushing or sharing review notes or the render ref between clones.
- New stacks, new checks, new principles.
- Changes to adoption beyond its interview scope and the plan's path.

## By hand, for projects alpha already set up

To be confirmed while building, and repeated in the final report:

1. The old kit has no uninstall, and the new one can't read the old answers yet, so switch the old hooks off by hand: remove alpha's hook entries from `.claude/settings.json` and run `git config --unset core.hooksPath`.
2. Move `docs/principles.toml` and `docs/dependencies.md` to `docs/alpha/`, and fold `docs/specification.md`, `docs/glossary.md`, `docs/design-language.md` and `docs/adoption.md` into `docs/alpha/` (the old `docs/specs/` features into `docs/alpha/features/`).
3. Remove `manifest` from `.claude/alpha/project.json` and reshape the answers (identity's target users and requirements into `requirements`, `security.auth` into `auth`, drop the review mode, thresholds, `testing.run` and `testing.mutants`), then `alpha answers check` until ok.
4. Run `alpha apply`: with no base ref, every differing file is a proposal to merge by hand. Then `alpha bootstrap` and `alpha commit`.
