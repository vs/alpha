# alpha

alpha is a Claude Code plugin that interviews you about a new project and generates a skeleton: config, docs, test wiring and enforcement, with no app code. `/alpha:adopt` brings an existing repo under the same enforcement, with baselines for its legacy findings and a compliance plan it then works through (spec §5b). Design: [docs/superpowers/specs/2026-10-19-project-kit-design.md](docs/superpowers/specs/2026-10-19-project-kit-design.md).

## Dev commands

- `mise install`, then `mise run check`: every check the kit runs on itself (typos, rumdl and agnix on the docs and skills, then pytest, ruff and pyright).
- `uv run pytest`
- `uv run ruff check` and `uv run ruff format`
- `uv run pyright`
- `bin/alpha generate|bootstrap|commit-skeleton <folder>`: a new project from finished answers (`answers check` first; `answers write <target> --json '…'` saves an area). `bin/alpha update <project> [--dry-run]`, then `bin/alpha commit-update <project>`, merges changed answers into a generated or adopted project, and upgrades one an older kit set up to this kit (spec §5a, decision 0022).
- `bin/alpha recipe list|check|try|save`, `bin/alpha registry list|show|stale` and `bin/alpha defaults show|set`: the kit's stacks and drafted recipes, the reviewed tool registry (`stale` names tools not reviewed in 180 days) and the merged defaults.
- `bin/alpha adopt survey <repo> [--save]`: what an existing repo already has, in facts (spec §5b): candidate components from the recipes' `[detect]` markers, the files `defaults/survey.toml` names, branch, clean tree and commit convention. An adopted recipe (`"adopted": true`, optionally `"extends": "<kit stack>"`) runs the repo's own tools; `alpha recipe try` proves it on a throwaway worktree of the repo's HEAD, where a failing check passes only if its baseline reader reads its findings.
- `bin/alpha adopt apply <repo> [--dry-run]`: with finished adoption answers, writes alpha's files onto the repo on `alpha/adopt` (from the default branch): new files, a mechanical merge of `.gitignore` and `.claude/settings.json`, and a two-sided proposal for every other file the repo already has, merged by hand as `/alpha:extend` does. Then `alpha bootstrap <repo> --capture-baselines` and `alpha commit-update`. `adoption.git_hooks` is `alpha` (alpha sets `core.hooksPath`) or `chain` (the repo's hook manager calls alpha's commit-msg check). A kit recipe's `[adopt]` table holds the command variants an adopted recipe uses, so a root component's tools skip `.claude/`.
- `bin/alpha adopt gaps|next|start|done|drop <repo>`: the compliance plan of an adopted repo (spec §5b, step 6), kept in `adoption.steps` and rendered as `docs/adoption.md`. `gaps [--save]` adds the mechanical steps (chained hooks, formatting, missing checks and coverage, a burn-down per baseline); `next` names the next ready step; `done` marks a step only when every condition of its acceptance holds (`run`, `recipe`, `no_baseline`, `commit_hook`, `confirm` with `--confirmed-by-user`); `drop --decision N` needs an accepted record naming the step. Then `alpha update` and `alpha commit-update` refresh the doc.
- `bin/alpha baseline show|capture|tighten <project>`: the per-file, per-rule baselines of legacy findings (spec §8b). Only a project whose answers list `adoption.baselines` has any. `alpha bootstrap <project> --capture-baselines` records the missing ones once each toolchain is installed. The patterns that read each tool's findings are matched against real output in `tests/fixtures/baseline-output/`; re-record those when a pinned tool's version changes.
- `bin/alpha-evals run [scenario ...]`: the interview evals (spec §12). Each scenario runs the real `/alpha:new-project` headlessly, with a simulated user answering from `evals/briefs/<scenario>.toml`, then checks the generated skeleton and probes the reviewer. It spends real tokens: each call gets the scenario's remaining `--max-usd` budget ($20 by default), and a call that fails or times out counts as $0, so check the cost column in the `summary.md` it prints. The $20 default stops an Opus interview before generation (see below); a complete run needs about `--max-usd 60`, or a cheaper `--interviewer-model`. `bin/alpha-evals check <project> <scenario>` reruns only the skeleton checks.

## Rules

- The kit follows its own principles (spec §12).
- Commits use conventional commits with the scopes `git.scopes` lists (alpha, hooks, recipes, defaults, spec). The description after the `type(scope):` prefix is at most 50 chars, imperative, capitalized, no trailing period. Body lines wrap at 72.

## Principles

- **Simplest sufficient architecture**: As simple as possible, as complex as the problem requires.
- **Fail fast, fail helpfully**: Detect errors as early as possible. Every error message describes the problem and tells the user how to proceed.
- **Tests are as important as the core**: Test design and writing get the same effort and intensity as the logic. Tests trace back to acceptance checks. Risky logic (a branch, a parser, money, security, data writes, a bug fix) gets a test that fails when it breaks: one good test, not coverage. A trivial change (a rename, a constant, wiring) may go without one, with the reason recorded.
- **Docs move with the code**: A change to public behavior updates the docs in the same change.
- **Build and hosting are decided up front**: Build and hosting are decided up front and runnable in CI. (overridden: see docs/decisions/0021-no-ci-checks-run-locally.md)
- **Validate at the edges, trust the inside**: External input is parsed into typed data once, at the boundary. Inside, code doesn't re-check what its own modules return; each remaining cast or runtime check says which boundary or invariant it serves.
- **Strict types**: TypeScript `strict`, Python type-checked in strict mode.
- **Logic in the middle, side effects at the edges**: Business logic is kept pure and in the middle; side effects live at the edges.
- **No dead code**: No commented-out code, no speculative options.
- **Code over comments**: A comment stays only for what the code can't say: a license header, a rule set by a dependency, platform or protocol we can't change, a public API's contract, an issue link for a constraint, or a `shortcut: <the limit>, <when to upgrade>` note on a deliberate shortcut. Anything surprising in our own code is fixed by renaming, extracting or retyping it until it reads plainly, not explained in prose.
- **Generated files come from their source**: A generated file changes only by changing its source and regenerating it, never by hand.
- **One vocabulary**: A glossary, and consistent names across code, docs, and UI.
- **One command each to set up, test, and run**: One command each to set up, test, and run, per component, on a fresh machine.
- **Reproducible**: Pinned dependencies and lockfiles. For ML: seeds, data versions, recorded experiment configs.
- **Every external call has a timeout and a failure path**: Every external call has a timeout and a failure path. Retries only on safe-to-repeat operations.
- **Performance budgets**: Performance budgets set in the interview are enforced.
- **Safe migrations**: Every schema change is a migration, reversible where possible.
- **No secrets in the repo**: Secrets come from the environment or a secret store.
- **Every new dependency has a recorded reason**: Every new dependency has a recorded reason and is pinned.
- **Clean, readable history**: Each commit is one logical change, holds only the files changed for it, passes checks on its own, and has a message that explains why.
- **Evidence before "done"**: No claim of success without running the check that shows it.
- **Never weaken a check to pass it**: No skipped tests, loosened lint, or catch-all exception handlers, and no mocking the thing under test. A type error from an outdated dependency is fixed by upgrading it, not by removing or downgrading code. If a check is wrong in one place, record why in a decision that names the path and the rule, then make the exception there.
- **Stay in scope**: No drive-by refactors of code the task doesn't touch.
- **Subtract before you add**: In the code a task touches, first remove what's dead there: unused code, redundant checks, stubs. A new internal API replaces the old one in the same change: every caller migrated, the old one deleted, no compatibility layer.
- **Smallest complete change**: Take the first option that fully works: skip what nobody asked for, then reuse what the codebase has, then the standard library or platform, then an installed dependency, then one line a reader gets at a glance, and only then new code. No new dependency for a few lines, and no abstraction, wrapper, option, config or "for later" code nobody asked for; keep values in the form the platform already gives you, and keep the structure the codebase already has. Never cut validation at trust boundaries, error handling that prevents data loss, security, accessibility, or anything the user asked for.
- **Scope before writing**: Before changing code, list every place the change must reach (callers, tests, fixtures, config, exports) and what it could break for users (data lost or exposed, callers that stop working), then finish every part of it. Features nobody asked for aren't scope.
- **Fix bugs at the root**: Before a bug fix, find every caller of the function it touches and fix the root cause once, in the shared code, not in one caller. Code that is moved or merged keeps its error handling and validation.
- **Lean structure**: Near-copies that must change together are merged into one. A function is split by job, never by line count, and never into helpers that only make it shorter. Between options of equal size, the one that is correct on edge cases wins.
- **Never block on the human**: Don't stop to ask about reversible work. When a requirement is ambiguous, make the reasonable choice, record it in the decision log, and say what you chose. Ask first only when the choice sets product direction or can't be undone: rewriting the main branch, deploys, deleting data, messages to people.
- **Definition of done**: Tests written and passing, types and lint clean, docs updated, committed per the history principle, reviewer passed.

`docs/principles.toml` is the source of truth, with each principle's parameters, rationale and overrides.

## Working rules

- Before you change code, docs or config, read the decision records in docs/decisions/ that bear on the change (an index is added to your context at the start of each session) and the principle's parameters in docs/principles.toml. Follow them.
- A change that contradicts an accepted decision needs a new decision that supersedes it, recorded with the decision skill. A `Kind: technical` record you may supersede yourself, giving the reason; ask the user first for a `Kind: product` record or one that changes a principle.
- When a requirement is ambiguous, make the reasonable choice, record it with the decision skill and say what you chose; don't stop to ask about reversible work. Ask first only about product direction or what can't be undone (rewriting main, deploys, deleting data, messages to people).
- Read a file in full before you edit it, and every file a wide change touches; search snippets aren't enough.
- Look up a dependency's API in its installed source or types instead of guessing it.
- Remove dead code and replaced internal APIs without asking, but ask before removing code or behavior that looks intentional.
- Commit only the files you changed for the work, staged by path. Other changes in the tree may be the user's or another session's, so don't stage, stash or reset them; the hooks block the commands that would.
- Subagents work under the same principles, decisions and checks.
- Before you report work as done, re-read every changed file top to bottom as a stranger would.
- At the end of a planned piece of work, run the principles-reviewer agent.
- When you add a code generator, add a `generate` task to `mise.toml` and to the `ci` task's `depends`; commit what it regenerates with the change.
- Never disable a lint rule to pass; an exception names one path and one rule, and a decision record that names that path gives the reason.
- A security suppression (osv-scanner, betterleaks) needs a reason and a review date: in the `osv-scanner.toml` next to the lockfile it applies to, `ignoreUntil` and `reason`; in `.betterleaksignore`, a `# <reason> (review YYYY-MM-DD)` line directly above the entry.

## Communication

- Answer a question before making edits or running commands for it.
- When responding to feedback or a review, say first whether you agree, then what you changed.
- Be concise and direct: plain technical prose, no filler, no emojis. Define jargon you can't avoid.
- Explain a non-trivial problem or design as the problem, a concrete example or short trace, then the solution and why it's needed.
- When you report finished work, end with one or two lines: what you skipped or didn't check, and any risk the user must know.

## Stack rules

### alpha-python (alpha)

- **alpha-python:uv-for-dependencies**: Add and remove dependencies with `uv add` and `uv remove`, never by editing the dependency lists in `pyproject.toml` or with `pip`.
- **alpha-python:typed-boundaries**: Parse external input (JSON, files, environment, requests) into dataclasses or typed models at the boundary; don't pass `dict[str, Any]` inward.
- **alpha-python:import-contracts**: Once a component has more than one package, add import-linter contracts for the layers `docs/architecture.md` names, and add `lint-imports` to its `structure` command.

## Commands

### alpha (alpha-python, `./`)

Code: `**/*.py`. Tests: `tests/**/*.py`, `**/test_*.py`, `**/*_test.py`, `**/conftest.py`. Not checked: `**/.*/**`, `**/__pycache__/**`, `**/build/**`, `**/dist/**`.

| Step | Command |
|---|---|
| setup | `uv sync` |
| test | `uv run pytest` |
| lint | `uv run ruff check src tests project-files` |
| format | `uv run ruff format src tests project-files` |
| format_check | `uv run ruff format --check src tests project-files` |
| typecheck | `uv run pyright` |
| structure | `uv run deptry . --extend-exclude .claude` |
| run | add when the entry point exists |

Run every check: `mise run check`.

## Definition of done

1. Tests written and passing.
2. Types and lint clean.
3. Docs updated.
4. Committed per the commit convention.
5. Reviewer passed.

## Commits

Follow the commit skill (`.claude/skills/commit/SKILL.md`, which the user runs as /commit). Convention: conventional commits, scopes: alpha, hooks, recipes, defaults, spec, or another area it touches, enforced by the commit-msg hook. Work on a short-lived branch and open a pull request into main; don't commit to main directly.

## Docs

- [Principles](docs/principles.toml)
- [Product](docs/product.md)
- [Architecture](docs/architecture.md)
- [Build, CI and hosting](docs/build.md)
- [Security](docs/security.md)
- [Dependencies](docs/dependencies.md)
- [Decisions](docs/decisions/)
- [Contributing](CONTRIBUTING.md)
- [Glossary](docs/glossary.md)
- [Data](docs/data.md)
- [Performance](docs/performance.md)
- [Releases](docs/releases.md)
- [Adoption plan](docs/adoption.md): the steps that bring this repo's code up to the principles; `/alpha:adopt` resumes it

## Install and verify

Try alpha without installing it: start Claude Code with the plugin loaded for that session only, then run the interview on a new folder.

```sh
claude --plugin-dir ~/workspace/alpha
/alpha:new-project ~/code/my-new-project
```

To bring an existing repo in, run `/alpha:adopt ~/code/that-repo` (clean tree, committed code); it installs on branch `alpha/adopt`, and running it again in the adopted repo carries out the next step of `docs/adoption.md`.

To change a project alpha generated (add a component, revisit an area's decisions), run `/alpha:extend <what to change>` from inside it. It re-asks only what the change affects, merges alpha's files without overwriting your edits, and commits.

Optional: to stop Claude Code asking before each alpha CLI call during the interview, add `"Bash(<alpha checkout>/bin/alpha *)"` with the absolute path of this checkout to `permissions.allow` in `~/.claude/settings.json` (for an installed plugin, use the `bin/alpha` path the prompt shows).

Install it for every session from GitHub with `claude plugin marketplace add vs/alpha`, then `claude plugin install alpha@alpha`; update with `claude plugin marketplace update alpha` and `claude plugin update alpha@alpha`. `claude plugin validate .claude-plugin/marketplace.json` checks the manifests.

Recipes, defaults and the tool registry come from the plugin itself: the installed copy, or this checkout under `--plugin-dir`. Only `ALPHA_SOURCE` points alpha at another checkout (the evals set it to the kit commit they test); for a stack both have, that checkout's recipe wins, and one from before the quality gates has tag-pinned recipes the plugin refuses, with an error that says to `git pull` it or unset `ALPHA_SOURCE`.

The user's own layer is `~/.config/alpha/` (`ALPHA_CONFIG_DIR` overrides it; the tests and evals point it at a temp folder): `overrides.toml` and `CHANGELOG.md` from `alpha defaults set`, and `recipes/` from `alpha recipe save`. It applies on top of the kit, and the kit's recipe wins for a stack both have. Nothing there is committed.

Kit tests: `uv run pytest` runs the fast suite. `uv run pytest -m slow` also bootstraps real projects with uv and pnpm (needs both installed and network access).

What each live run of the kit verified, and what stayed open: [docs/live-checks.md](docs/live-checks.md).
