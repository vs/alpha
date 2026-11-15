# alpha

alpha is a Claude Code plugin that interviews you about a new project and generates a skeleton: config, docs, test wiring and enforcement, with no app code. `/alpha:adopt` brings an existing repo under the same enforcement, with baselines for its legacy findings and a compliance plan it then works through (spec §5b). Design: [docs/superpowers/specs/2026-10-19-project-kit-design.md](docs/superpowers/specs/2026-10-19-project-kit-design.md).

## Dev commands

- `mise install`, then `mise run check`: every check the kit runs on itself (typos, rumdl and agnix on the docs and skills, then pytest, ruff and pyright).
- `uv run pytest`
- `uv run ruff check` and `uv run ruff format`
- `uv run pyright`
- `bin/alpha status <folder>`: the folder's state for `/alpha:install` (empty, existing, installed, hooks-off, …).
- `bin/alpha uninstall <project>` and `bin/alpha hooks on <project>`: switch alpha's hooks off and back on, deleting no file and committing nothing. Off takes alpha's entries out of `.claude/settings.json` and unsets `core.hooksPath` (or, in chain mode, moves the call between `# alpha:begin` and `# alpha:end` out of the hook manager's commit-msg file into `.claude/alpha/state/chain.json`); on restores the hooks table as it was when nothing changed since, else merges alpha's entries back.
- `bin/alpha apply <folder> [--dry-run]`, then `bin/alpha bootstrap <folder>` and `bin/alpha commit <folder>`: writes alpha's files from finished answers (`answers check` first; `answers write <target> --json '…'` saves an area). On an empty folder it sets up a new project; on an existing repo it adopts it on `alpha/adopt`; on an installed project it is `bin/alpha update <project> [--dry-run]`, which merges changed answers and a newer kit against the render alpha last committed (kept in git: `refs/alpha/rendered` and notes under `refs/notes/alpha-rendered`, never in project.json). alpha's own files (hooks, checks, the git hook, the copied agents and skills) are always replaced.
- `bin/alpha recipe list|check|try|save`, `bin/alpha registry list|show|stale` and `bin/alpha defaults show|set`: the kit's stacks and drafted recipes, the reviewed tool registry (`stale` names tools not reviewed in 180 days) and the merged defaults.
- `bin/alpha adopt survey <repo> [--save]`: what an existing repo already has, in facts (spec §5b): candidate components from the recipes' `[detect]` markers, the files `defaults/survey.toml` names, branch, clean tree and commit convention. An adopted recipe (`"adopted": true`, optionally `"extends": "<kit stack>"`) runs the repo's own tools; `alpha recipe try` proves it on a throwaway worktree of the repo's HEAD, where a failing check passes only if its baseline reader reads its findings.
- `bin/alpha apply <repo>` with finished adoption answers writes alpha's files onto the repo on `alpha/adopt` (from the default branch): new files (with the skeleton of each component that is on a kit or drafted recipe and has no manifest yet), a mechanical merge of `.gitignore` and `.claude/settings.json`, and a two-sided proposal for every other file the repo already has, merged by hand as `/alpha:extend` does. Then `alpha bootstrap <repo> --capture-baselines` and `alpha commit`. `adoption.git_hooks` is `alpha` (alpha sets `core.hooksPath`) or `chain` (the repo's hook manager calls alpha's commit-msg check). A kit recipe's `[adopt]` table holds the command variants an adopted recipe uses, so a root component's tools skip `.claude/`.
- `bin/alpha adopt gaps|next|start|done|drop <repo>`: the compliance plan of an adopted repo (spec §5b, step 6), kept in `adoption.steps` and rendered as `docs/alpha/adoption.md`. `gaps [--save]` adds the mechanical steps (chained hooks, formatting, missing checks and coverage, a burn-down per baseline); `next` names the next ready step; `done` marks a step only when every condition of its acceptance holds (`run`, `recipe`, `no_baseline`, `commit_hook`, `confirm` with `--confirmed-by-user`); `drop --reason '…'` needs the reason the user agreed to. Then `alpha update` and `alpha commit` refresh the doc.
- `bin/alpha baseline show|capture|tighten <project>`: the per-file, per-rule baselines of legacy findings (spec §8b). Only a project whose answers list `adoption.baselines` has any. `alpha bootstrap <project> --capture-baselines` records the missing ones once each toolchain is installed. The patterns that read each tool's findings are matched against real output in `tests/fixtures/baseline-output/`; re-record those when a pinned tool's version changes.

## Rules

- The kit follows its own principles (spec §12).
- Commits use conventional commits with the scopes `git.scopes` lists (alpha, hooks, recipes, defaults, spec). The description after the `type(scope):` prefix is at most 50 chars, imperative, capitalized, no trailing period. Body lines wrap at 72.

## Principles

- **Simplest sufficient architecture**: As simple as possible, as complex as the problem requires.
- **Fail fast, fail helpfully**: Detect errors as early as possible. Every error message describes the problem and tells the user how to proceed.
- **Tests are as important as the core**: Test design and writing get the same effort and intensity as the logic. Tests trace back to acceptance checks. Risky logic (a branch, a parser, money, security, data writes, a bug fix) gets a test that fails when it breaks: one good test, not coverage. A trivial change (a rename, a constant, wiring) may go without one, with the reason recorded.
- **Docs move with the code**: A change to public behavior updates the docs in the same change.
- **Build and hosting are decided up front**: Build and hosting are decided up front and runnable in CI. (overridden: see CONTRIBUTING.md, Overrides)
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
- **Never weaken a check to pass it**: No skipped tests, loosened lint, or catch-all exception handlers, and no mocking the thing under test. A type error from an outdated dependency is fixed by upgrading it, not by removing or downgrading code. If a check is wrong in one place, add a row to CONTRIBUTING.md's Exceptions table that names the path, the rule and why, then make the exception there.
- **Stay in scope**: No drive-by refactors of code the task doesn't touch.
- **Subtract before you add**: In the code a task touches, first remove what's dead there: unused code, redundant checks, stubs. A new internal API replaces the old one in the same change: every caller migrated, the old one deleted, no compatibility layer.
- **Smallest complete change**: Take the first option that fully works: skip what nobody asked for, then reuse what the codebase has, then the standard library or platform, then an installed dependency, then one line a reader gets at a glance, and only then new code. No new dependency for a few lines, and no abstraction, wrapper, option, config or "for later" code nobody asked for; keep values in the form the platform already gives you, and keep the structure the codebase already has. Never cut validation at trust boundaries, error handling that prevents data loss, security, accessibility, or anything the user asked for.
- **Scope before writing**: Before changing code, list every place the change must reach (callers, tests, fixtures, config, exports) and what it could break for users (data lost or exposed, callers that stop working), then finish every part of it. Features nobody asked for aren't scope.
- **Fix bugs at the root**: Before a bug fix, find every caller of the function it touches and fix the root cause once, in the shared code, not in one caller. Code that is moved or merged keeps its error handling and validation.
- **Lean structure**: Near-copies that must change together are merged into one. A function is split by job, never by line count, and never into helpers that only make it shorter. Between options of equal size, the one that is correct on edge cases wins.
- **Never block on the human**: Don't stop to ask about reversible work. When a requirement is ambiguous, make the reasonable choice, write it into the docs, and say what you chose. Ask first only when the choice sets product direction or can't be undone: rewriting the main branch, deploys, deleting data, messages to people.
- **Definition of done**: Tests written and passing, types and lint clean, docs updated, committed per the history principle, reviewer passed.

`docs/principles.toml` is the source of truth, with each principle's parameters, rationale and overrides.

## Working rules

- Before you change code, docs or config, read the parts of docs/specification.md and CONTRIBUTING.md that bear on the change and the principle's parameters in docs/principles.toml. Follow them.
- A decision updates the docs, as the decision skill says: what the product does goes in docs/specification.md and needs the user's yes; how the work is done goes in CONTRIBUTING.md, with the reason in the commit; a changed principle is an override in the answers, which the user agrees to first.
- When a requirement is ambiguous, make the reasonable choice, record it with the decision skill and say what you chose; don't stop to ask about reversible work. Ask first only about product direction or what can't be undone (rewriting main, deploys, deleting data, messages to people).
- Read a file in full before you edit it, and every file a wide change touches; search snippets aren't enough.
- Look up a dependency's API in its installed source or types instead of guessing it.
- Remove dead code and replaced internal APIs without asking, but ask before removing code or behavior that looks intentional.
- Commit only the files you changed for the work, staged by path. Other changes in the tree may be the user's or another session's, so don't stage, stash or reset them.
- Subagents work under the same principles, docs and checks.
- Before you report work as done, re-read every changed file top to bottom as a stranger would.
- At the end of a planned piece of work, run the principles-reviewer agent.
- When you add a code generator, add a `generate` task to `mise.toml` and to the `ci` task's `depends`; commit what it regenerates with the change.
- Never disable a lint rule to pass; an exception names one path and one rule, and a row in CONTRIBUTING.md's Exceptions table names that path, the rule and the reason.
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
- **alpha-python:import-contracts**: Once a component has more than one package, add import-linter contracts for the layers the architecture in `docs/specification.md` names, and add `lint-imports` to its `structure` command.

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

The hooks leave the full test suites to one checkpoint: before your work reaches main (a push to main, or merging a pull request), run `python3 .claude/alpha/hooks/stop_checks.py tests`. It runs the suite of each component you changed and remembers a pass until those files change. While you work, run the tests your change touches.

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
- [Specification](docs/specification.md): what the product does, settled as the work needs it; each feature adds its own spec in `docs/specs/`
- [Contributing](CONTRIBUTING.md): how the project is built, checked, released and kept secure
- [Dependencies](docs/dependencies.md)
- [Glossary](docs/glossary.md)
- [Adoption plan](docs/adoption.md): the steps that bring this repo's code up to the principles; `/alpha:adopt` resumes it

## Install and verify

Try alpha without installing it: start Claude Code with the plugin loaded for that session only, then run the interview on a new folder.

```sh
claude --plugin-dir ~/workspace/alpha
/alpha:new-project ~/code/my-new-project
```

To bring an existing repo in, run `/alpha:adopt ~/code/that-repo` (clean tree, committed code); it installs on branch `alpha/adopt`, and running it again in the adopted repo carries out the next step of `docs/adoption.md`.

To change a project alpha generated (add a component, revisit an area's decisions), run `/alpha:extend <what to change>` from inside it. It re-asks only what the change affects, merges alpha's files without overwriting your edits, and commits.

To work a task in a generated or adopted project, run `/alpha:go <task>`. It follows a playbook from `skills/go/playbooks/`; a feature goes through a spec in `docs/specs/` that the user approves before any code. The interview settles only the setup areas; the spec areas start `open` and `/alpha:go` settles each when the work needs it.

Optional: to stop Claude Code asking before each alpha CLI call during the interview, add `"Bash(<alpha checkout>/bin/alpha *)"` with the absolute path of this checkout to `permissions.allow` in `~/.claude/settings.json` (for an installed plugin, use the `bin/alpha` path the prompt shows).

Install it for every session from GitHub with `claude plugin marketplace add vs/alpha`, then `claude plugin install alpha@alpha`; update with `claude plugin marketplace update alpha` and `claude plugin update alpha@alpha`. `claude plugin validate .claude-plugin/marketplace.json` checks the manifests.

Recipes, defaults and the tool registry come from the plugin itself: the installed copy, or this checkout under `--plugin-dir`. Only `ALPHA_SOURCE` points alpha at another checkout; for a stack both have, that checkout's recipe wins, and one from before the quality gates has tag-pinned recipes the plugin refuses, with an error that says to `git pull` it or unset `ALPHA_SOURCE`.

The user's own layer is `~/.config/alpha/` (`ALPHA_CONFIG_DIR` overrides it; the tests point it at a temp folder): `overrides.toml` and `CHANGELOG.md` from `alpha defaults set`, and `recipes/` from `alpha recipe save`. It applies on top of the kit, and the kit's recipe wins for a stack both have. Nothing there is committed.

Kit tests: `uv run pytest` runs the fast suite. `uv run pytest -m slow` also bootstraps real projects with uv and pnpm (needs both installed and network access).

What each live run of the kit verified, and what stayed open: [docs/live-checks.md](docs/live-checks.md).
