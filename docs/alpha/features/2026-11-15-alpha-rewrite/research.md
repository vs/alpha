# alpha rewrite: research

Date: 2026-11-15

What the current implementation (main at 9edaa5c, kit 0.8.0) does, what each piece is for, which edge cases bit, and what the rewrite keeps, changes or drops. It is the source of knowledge for [the specification](specification.md) and [the plan](plan.md), not a structure to keep.

## 1. Inventory

About 42,500 lines in all: 10,000 in `src/alpha`, 1,700 in `src/alpha_evals`, 4,000 in the hooks and checks copied into projects, 2,000 in skills, 25,000 in tests.

| Part | Files | What it does |
|---|---|---|
| CLI | `src/alpha/cli.py` | argparse front for every subcommand: `answers`, `recipe`, `registry`, `defaults`, `adopt`, `baseline`, `generate`, `bootstrap`, `commit-skeleton`, `commit-update`, `update`. |
| Answers | `answers.py` (1,337), `core_areas.py` (710), `validate.py`, `areas.py` | Parses `.claude/alpha/project.json` into frozen dataclasses, area by area, with a message per error that names the field and the fix. 18 areas; 8 "spec areas" may be `open`. |
| Kit data | `defaults.py`, `registry.py`, `recipes.py` (858), `recipe_cli.py` | Kit defaults (`defaults/defaults.toml`) with the user layer (`~/.config/alpha/overrides.toml`) on top; the reviewed tool registry (`registry/tools.toml`, `registry/actions.toml`) with pins and `last_reviewed`; stack recipes (`recipes/*.toml` plus templates), drafted recipes proven by `recipe try` (a `proven_hash` of the recipe's own fields). |
| Principles | `principles.py` | Builds `docs/principles.toml` from the catalog in `defaults.toml`: which principles apply (traits, `settled_by` areas), their parameters, overrides, component commands and globs, protected paths, review settings, repo checks, baselines. The hooks read only this file. |
| Renderers | `render/docs.py`, `render/area_docs.py`, `render/tooling.py`, `render/ci.py`, `render/claude_settings.py`, `repo_checks.py` | CLAUDE.md, README, CONTRIBUTING, specification, glossary, design language, dependency log, adoption plan; mise.toml and the tool configs (typos, rumdl, lychee, betterleaks); GitHub Actions CI, scheduled workflow, Dependabot; `.claude/settings.json`. |
| Writing files | `generate.py`, `update.py` (620), `merge.py`, `gitops.py` | `generate` writes into an empty folder and records `manifest` in project.json: `files` (a sha256 per written file, which nothing reads), `applied` (a copy of the answers), `added` dates, kit version. `update` re-renders the `applied` answers as the base of a 3-way merge (`git merge-file`), and for an older kit fetches that kit's code and runs it in a subprocess (`_RENDER_OLD`). `gitops` commits in groups (docs, chore, tooling, one per component, ci, dependabot). |
| Adoption | `adopt.py` (781), `baseline.py` (473) | `survey` (candidate components from recipes' `[detect]` markers, hook managers, commit convention), `apply` onto `alpha/adopt` with `.gitignore` and `settings.json` merged mechanically and every other existing file as a two-sided proposal, the compliance plan (`gaps`, `next`, `start`, `done`, `drop`), baselines per file and rule. |
| Bootstrap | `generate.py` (`bootstrap`) | Per component: the recipe's bootstrap commands, then its checks; then `mise install` of the pinned tools and `mise run ci`; captures missing baselines once tools are installed. |
| Hooks | `project-files/hooks/*.py` | `session_start`, `subagent_start` (context), `guard_bash` (662), `guard_paths`, `post_edit`, `stop_checks` (936), `review` (827), `review_record`, `user_prompt`, `commit_msg`, `_common` (562). |
| Checks | `project-files/checks/*.py` | `secret_scan` (betterleaks on non-ignored files only), `diff_checks` (immutable migrations, squawk, baselines on a PR), `ratchet` (baseline reader), `review_dates`, `palette`, `shortcuts`. |
| Agents, skills copied | `project-files/agents`, `project-files/skills` | `principles-reviewer`, `committer`; `commit`, `decision`, `review-change`, `audit`, `debt`. |
| Plugin skills | `skills/` | `new-project`, `adopt`, `extend`, `go` (+ 9 playbooks), `fold-decisions`, `grilling`, `stack-recipe`, and 18 area skills. |
| Evals | `src/alpha_evals`, `bin/alpha-evals`, `evals/` | Headless interviews with a simulated user. Dropped by requirement 14. |

## 2. What a generated project holds today

Generated from `tests/fixtures/answers_valid.json` (59 files): root `CLAUDE.md`, `README.md`, `LICENSE`, `CONTRIBUTING.md`, `CHANGELOG.md`, `mise.toml`, tool configs (`_typos.toml`, `.rumdl.toml`, `lychee.toml`, `.betterleaks.toml`), `.gitignore`; `docs/principles.toml`, `docs/specification.md`, `docs/dependencies.md`, `docs/glossary.md`, `docs/design-language.md`, `docs/guide/README.md`; `.claude/` (settings, agents, skills, `alpha/hooks`, `alpha/checks`, `alpha/githooks/commit-msg`, `alpha/project.json`); `.github/` (ci, scheduled, dependabot, jactionlint); per component, its manifest, configs and a setup test.

CLAUDE.md repeats every principle in prose, then working rules, communication rules, stack rules, a commands table per component, the definition of done, commits, and a docs list. The CI workflow calls `.claude/alpha/checks/*.py` through `mise run ci` tasks (secrets, migrations, review dates, palette, shortcuts), so a project without `.claude/alpha/` fails CI today.

## 3. Requirement by requirement

### 1. install

- Today's two entry points differ in their first check: `new-project` refuses any folder that holds more than `.DS_Store`, `.claude/alpha/project.json` and `.claude/settings.local.json`; `adopt` refuses a dirty tree, a detached HEAD, an existing `alpha/adopt` branch, ignore rules that cover alpha's files, and (with `git_hooks = alpha`) a repo that already runs its own git hooks.
- A repo with docs and no code yet goes through adoption today: the survey lists no candidate, and the interview generates each component's skeleton after one question. That covers "a non-empty folder without source code".
- Nothing today notices that the hooks are off. The SessionStart hook warns when `core.hooksPath` is wrong, but if `settings.json` lost its hook entries nothing runs to say so.

### 2. uninstall

- No uninstall exists. Hook entries are recognizable: every command alpha writes into `settings.json` runs `python3 "$CLAUDE_PROJECT_DIR"/.claude/alpha/hooks/<name>.py`.
- Guards today: `guard_bash` blocks `git config core.hooksPath` to any other value or `--unset`, and Bash writes to protected paths (redirects, `cp`, `mv`, `rm`, `tee`, `truncate`, `ln`, `install`, `sed -i`, `perl -i`). Nothing blocks an Edit of `settings.json` or of the hook scripts. A Claude that edits `stop_checks.py` to exit 0 switches the checks off.
- PR #46 (`53cabf0`) settled that the command guard catches habits, not evasion: any Bash guard is one script away from a bypass, so it doesn't parse `bash -c`, `eval` or wrappers. A CLI that edits `settings.json` itself is therefore not seen as a write, which is how `uninstall` gets past the guards with no special case.
- In `chain` mode (an adopted repo whose hook manager calls alpha's `commit-msg`), `core.hooksPath` isn't alpha's, so unsetting it would switch off the repo's own hooks.

### 3. purge

- `.claude/alpha/` holds hooks, checks, githooks, `project.json`, `baselines/` (adopted), `state/` and `notes/` (ignored).
- Kept files depend on alpha's: `mise.toml` tasks and the CI workflow call `.claude/alpha/checks/*.py`; an adopted component's commands may run through `ratchet.py`. A purge that keeps them as they are leaves a project whose `mise run ci` fails.
- The `.gitignore` alpha writes names `.claude/alpha/state/`, `.claude/alpha/notes/` and the hooks' `__pycache__`; harmless after a purge, but alpha's.

### 4. extend

- Re-asks only what a change affects, saves answers with one-line `answers write` calls (multi-line heredocs triggered permission prompts; see `docs/live-checks.md`, 2026-10-20), runs `update`, merges conflicts by hand, bootstraps new components, commits with `commit-update`.
- Moving a component's folder is the user's `git mv`; alpha refuses to move app code.

### 5. Scope of install

- The setup/spec split already exists (`docs/specs/2026-11-15-setup-first-spec-later.md`): 10 setup areas, 8 spec areas `open`, principles gated by `settled_by`. Identity still carries `target_users` and `requirements` (allowed empty), and security carries `auth` (allowed empty). The requirement moves those three into the product layer.
- `agent_workflow` today is review mode (`at-merge`, `batched`, `every-task`), thresholds (`max_lines`, `max_files`) and extra risk paths. With review only at merge (requirement 9), only the risk paths keep a job: a finding on one needs the user's agreement.

### 6. Where docs go

- `docs/specs/2026-11-15-one-process-doc-one-spec-doc.md` already put the process in `CONTRIBUTING.md` and the product in `docs/specification.md`, with glossary and design language as their own files (user decisions).
- The dependency log must stay its own file: the Stop hook checks that it changed when a lockfile did.
- `documentation.external = folder` makes alpha write `docs/guide/README.md` today, which requirement 6 rules out.
- `CHANGELOG.md` is written at the root when the releases area keeps one.

### 7. specify

- Today `/alpha:go`'s Specify playbook settles an open area through `/alpha:extend`, and the feature playbook settles each open area a feature touches before its spec. Requirement 7 says the product layer is worked on only when the user asks.

### 8. do

- `go` has 9 playbooks adapted from pstack's `poteto-mode` (MIT, credited in the skill). The feature playbook researches the code, grills, writes `docs/specs/<date>-<feature>.md` with a Requirements table naming a test per acceptance check, asks approval and native or subagent build, builds tests first, verifies, and ends with a whole-branch `review-change`.
- superpowers' brainstorming works one question at a time, proposes two or three approaches with a recommendation, presents the design in sections the user confirms, and writes a design doc before a separate implementation plan. Requirement 8 asks for that flow, plus deep research into how other projects build the feature, all under `docs/alpha/features/<date>-<feature>/`.

### 9 and 10. Review

- Today: `review.json` in `.claude/alpha/state/` (per checkout) holds `reviewed_tree`, findings and accepted ids; `review.py snapshot` writes the working tree into a private index to get a tree; `debt` counts lines and files since the reviewed tree; `gate` runs at every Stop and blocks in `batched` and `every-task` modes; the merge guard in `guard_bash` blocks `git push` to main and `gh pr merge`; `_carry` and `_carry_paths` move the reviewed tree across outside changes and alpha's own updates with `merge-tree`; `user_prompt.py` relays the user's `accept F-…`; `review_record.py` (SubagentStop) parses the reviewer's json, retrying the transcript for a hand-back.
- What bit (`docs/live-checks.md`, memory notes): the gate ran in cycles, each fix starting a new review; a reviewer resumed with SendMessage was never recorded; a session started in the main checkout couldn't record a review of a linked worktree, because the state lives in the checkout; the snapshot failed where `.gitignore` covers the state folder.
- The user approved earlier (2026-11-15): review once per branch before merge; a review's findings are the only blocker after it; fixes are checked against those findings only; no review at Stop.

### 11. update

Covered in section 6 below: the user chose (2026-11-15) to keep it, with a git-object base.

### 12. What stays

All listed pieces exist today. Notes per piece:

- The tool registry's `stale` lists tools not reviewed in 180 days; the weekly `toolchain` check runs `mise outdated`.
- Baseline readers are matched against recorded tool output in `tests/fixtures/baseline-output/`; Rust has no baseline readers yet (clippy and cargo print JSON lines).
- The Rust coverage run uses a dated nightly (`[vars] coverage_toolchain`); a monorepo's Rust components form one Cargo workspace; `cargo clippy` needs `--no-deps` per member.
- `secret_scan.py` exists because `betterleaks dir` also reads gitignored files such as `.env`.
- On the machine this runs on, the global mise config sets `RUSTUP_TOOLCHAIN`, which overrides a project's `rust-toolchain.toml`.
- Hooks must keep working with no dependencies. They are written to parse on Python 3.9 so `check_python()` can print its message; with Python 3.11 required by the kit, the late `tomllib` imports (three rows of the Exceptions table) can move to the top only if the hooks also require 3.11.

### 13. Fast checks

- `post_edit.py` runs the component's `format_file` and `lint_file` on the edited file. It does not type-check: the type check runs at Stop (`stop_checks.py`), with the structure check and the `stop = true` repository checks, cached per component tree and command.
- The full test suite runs at Stop only when `testing.run = at-stop`; the default `at-merge` leaves it to `stop_checks.py tests`, which remembers a pass per component tree.
- The only git hook is `commit-msg`.

### 14. Dropped

- Mutation testing: `recipes/rust.toml` (`mutants`, `cargo-mutants` in bootstrap, `mutants.out*/` ignore), `testing.mutants`, `ci:mutants`, the CI step, tests.
- `/debt` and `shortcuts.py` with its `check:shortcuts` task.
- `src/alpha_evals`, `bin/alpha-evals`, `evals/`, `tests/integration/evals/`, the two `BLE001` Exceptions rows.

### 15 and 16. Constraints

- `feat/no-decision-records` removed decision records; `fold-decisions` and `answers drop-decisions` exist only to migrate old projects.
- `manifest.files` (hashes) is written by `generate` and `update` and read by nothing but `refresh_manifest`, which rewrites it. `manifest.applied` is an answers copy, not hashes, but it goes too, with the git-object base.
- Gitignored state may hold hashes: the Stop cache keys on a sha256 of each component's files, `update.json` keeps conflict digests. Neither is committed.

## 4. Probes run for this research

- Git notes on tree objects: in a scratch repo, `git notes --ref=alpha-review add -m '{"findings":[]}' <tree>` stored a note on the tree; `git notes show <tree>` read it back, and a linked worktree read the same note, since `refs/notes/*` is shared between worktrees. This removes the worktree problem the current per-checkout `review.json` has.
- Generating `answers_valid.json` with the current CLI, to list what a project holds (section 2).

## 5. Prior art (from knowledge, not fetched for this research)

- git-appraise (Google) keeps code reviews in git notes under `refs/notes/devtools/*`; Gerrit writes review metadata as notes on commits (`refs/notes/review`). Both attach to commits. Attaching to the tree, as requirement 10 asks, makes a review survive a rebase or squash that keeps the content.
- pre-commit and husky uninstall by removing their hook files and git config, and leave the project's own config files alone. That matches requirement 2's split between uninstall (hooks only) and purge (files).

## 6. Settled with the user while researching (2026-11-15)

- `update` stays (CLI merges, skill resolves conflicts). Its base is alpha's last render, kept as a local git commit under `refs/alpha/rendered`; no answers copy in project.json and no running of an older kit. A clone without the ref gets two-sided proposals.
- uninstall and purge are not guarded against Claude running them: the skills are user-invocable only and CLAUDE.md says Claude runs them only when the user asks.
- The user then asked to take Claude's recommendation on every remaining open question while they are away. Those choices are marked "Claude's choice" in the specification's Decisions.
