# alpha

[![Claude Code plugin](https://img.shields.io/badge/Claude_Code-plugin-D97757?logo=claude&logoColor=white)](https://code.claude.com/docs/en/plugins)
[![Python recipe](https://img.shields.io/badge/recipe-Python-3776AB?logo=python&logoColor=white)](recipes/python.toml)
[![TypeScript recipe](https://img.shields.io/badge/recipe-TypeScript-3178C6?logo=typescript&logoColor=white)](recipes/typescript.toml)
[![Rust recipe](https://img.shields.io/badge/recipe-Rust-B7410E?logo=rust&logoColor=white)](recipes/rust.toml)
[![Any stack](https://img.shields.io/badge/recipe-any_stack-555)](skills/stack-recipe/SKILL.md)

alpha interviews you about a new project, then writes what agents build on:
principles, docs, Claude Code and git hooks, CI, and a test
setup per component that passes from the first commit. It writes no app code.
Each principle is checked, by a hook or by a reviewer agent that must pass
before a change reaches main.

The interview asks only what alpha needs to set up the tooling: the name,
license, components and stacks, tests, docs, CI, releases and git. What the
product does, its architecture, errors, UI, data, budgets and so on, stays
open until the work needs it; `/alpha:go` settles each part then, and
`docs/alpha/specification.md` lists what's still open.

```sh
claude plugin marketplace add vs/alpha
claude plugin install alpha@alpha
```

```text
/alpha:install ~/code/my-app
```

alpha asks one question at a time, each with a recommended answer. A choice
comes in Claude Code's question dialog, the recommendation first; a draft,
such as the project's name or value proposition, comes as text ending in the
recommended answer, for you to confirm or rewrite.

## What you get

| | |
|---|---|
| `docs/alpha/principles.toml` | the one file CLAUDE.md, hooks and reviewer read |
| `docs/alpha/specification.md` | what the product does: requirements and the parts settled so far, the rest listed as not settled yet; features add their own specs in `docs/alpha/features/` |
| `CONTRIBUTING.md` | how the project is set up, checked, committed, built, released and kept secure |
| `.claude/` | permissions, hooks, the principles reviewer, skills to commit, record a decision in the docs, and review a change, the whole repo or its `shortcut:` ledger |
| each component | strict lint, types and tests, wired up with no `src/`; a monorepo's Rust components form one Cargo workspace at the root |
| `mise.toml` | the repository checks, tools pinned: `mise run ci` runs them (secrets, typos, markdown, links, action pins, agent config) |
| `.github/` | CI running the same checks, a weekly scheduled run, Dependabot |
| `docs/alpha/design-language.md` | optional: one look for every visual, from diagrams in the docs to the UI, which the reviewer holds each changed visual to |

The design language is yours to skip. Settle it when you need it
(`/alpha:go settle the design language`: character, palette, typography,
shape, imagery, diagram style) and it becomes a principle that CLAUDE.md
states, and the source of the UI's tokens. Until then, alpha enforces and
recommends nothing about how visuals look. Which files count as visuals is the `[visuals]`
list in `docs/alpha/principles.toml` (diagram sources, SVG, styles, tokens, chart
specs; docs and UI markup when a change touches something visual; images and
fonts are named but can't be read). Settling it asks for the paths of
third-party assets, such as partner logos, and leaves them out.

It guides; it isn't a wall. A visual may step outside it for a stated reason,
and only drift is a finding. You choose how firmly colors are held: `advise`
(the default) shows the reviewer each color outside the palette to judge,
`enforce` adds a `palette` check that fails on one, `off` does neither.

## Exhaustive testing, if you ask

For a project that must not fail, say yes to exhaustive testing in the
interview (or later: `/alpha:extend test this exhaustively`). alpha adds a
principle modeled on [how SQLite is tested](https://www.sqlite.org/testing.html):
every branch taken both ways, every failure forced by injecting it, fuzz or
property-based tests for outside input, limits tested on both sides, a
failing test before each bug fix, invariants asserted in the code. The
reviewer holds every change to it, and CI fails a pull request that leaves a
changed line or branch uncovered. It is off by default.

Rust coverage records branches too: only the coverage run uses a pinned,
dated nightly, since stable Rust reports none.

## Needs

[uv](https://docs.astral.sh/uv/) and [pnpm](https://pnpm.io/) for the Python
and TypeScript components, [rustup](https://rustup.rs/) for Rust ones, and
[mise](https://mise.jdx.dev/) to install and run the repository checks. A
component on another stack (Go, say) needs its own toolchain installed too.

## Bring an existing repo in

```text
/alpha:install ~/code/old-service
```

alpha surveys the repo and interviews you with what it already does as the
recommendations. Then it installs the same enforcement on a branch,
`alpha/adopt`, keeping the repo's own tools where they meet the principles. A
part that has docs but no build files yet gets the skeleton a new project
would, after one question.
Today's lint, type, test and docs findings are baselined, so only new ones
fail, and a baseline only shrinks. What's left is a compliance plan in
`docs/alpha/adoption.md`: run `/alpha:install` again to work through it one step at a
time, each step done only when its check passes.

## Change it later

```text
/alpha:extend add a worker component
```

It asks again only what the change affects, and merges into files you edited.

## Work in it

```text
/alpha:go add CSV export to the report command
```

alpha picks a playbook for the task (investigation, feature, bug fix,
refactoring, perf, specify, prototype, session pickup or pause) and follows
it step by step, keeping the project's principles, docs and
checks. `/alpha:go settle the performance budgets` settles a part of the
specification left open, as do `settle the target users` and `settle the
auth`; a feature that needs one asks about it with its other questions. A feature starts with research and questions, then a spec in
`docs/alpha/features/<date>-<feature>/` that names a test for each acceptance
check. Nothing is built until you approve it and choose how: native, where
Claude builds every task, or with subagents, where a fresh one builds each
task and another reviews it. Each task's tests are written first and fail
before the code makes them pass. Work can run in its own git worktree. The
playbooks live in the plugin, not in your project.

## Decisions live in the docs

A project keeps no decision records. A choice changes the doc it governs:
what the product does in `docs/alpha/specification.md`, how the work is done in
`CONTRIBUTING.md`, a loosened principle as an override listed there, an
exception to a check as a row of its Exceptions table, and an accepted review
finding as an `Accepts:` trailer on a commit. Git history keeps when and why.

## Update

```sh
claude plugin marketplace update alpha
claude plugin update alpha@alpha
```

Your projects move to the new kit with the plugin's `bin/alpha update
<project>` (try `--dry-run` first), then `bin/alpha commit <project>`;
Claude finds `bin/alpha` for you if you ask it to update the project to the
new alpha. alpha merges its
newer hooks, checks and files into yours and keeps your edits; where they
overlap, it leaves a proposal for you to merge by hand.

## Switching the hooks off

`bin/alpha uninstall <project>` is the one way to switch alpha's hooks off: it
takes alpha's hook entries out of `.claude/settings.json` and its commit-msg
hook out of git (`core.hooksPath`, or the call between `# alpha:begin` and
`# alpha:end` in your own hook manager's file). It deletes no file and commits
nothing. `bin/alpha hooks on <project>` puts back what it took out, as
`/alpha:install` does when it finds the hooks off.

`bin/alpha purge <project>` removes alpha altogether, in one commit: it
uninstalls the hooks, deletes `.claude/alpha/`, `docs/alpha/` and alpha's
agents and skills (even edited ones), and takes out only what points at them
from the files you keep: lines in `CLAUDE.md`, `CONTRIBUTING.md` and
`README.md`, alpha's entries in `.claude/settings.json`, the tool configs,
`.gitignore`, and the `mise.toml` tasks that ran alpha's scripts. Your
components' scaffolding stays, so the project still builds and tests. A file
it can't clean stops it before it writes anything, naming the line to fix.

When you override a default, alpha asks whether to keep it for your next
projects. A yes goes to `~/.config/alpha/overrides.toml`, a recipe drafted in
an interview to `~/.config/alpha/recipes/`. Both apply on top of the installed
plugin and survive its updates.

## Projects an older alpha set up

An alpha before 1.0 kept a `manifest` in `.claude/alpha/project.json`; this
alpha doesn't upgrade such a project on its own. By hand, in one sitting:

1. Move `docs/principles.toml` and `docs/dependencies.md` into `docs/alpha/`,
   and fold `docs/specification.md`, `docs/glossary.md`,
   `docs/design-language.md` and `docs/adoption.md` into `docs/alpha/`; old
   feature specs in `docs/specs/` go to `docs/alpha/features/`.
2. Remove `manifest` from `project.json` and reshape the answers: identity's
   target users and requirements go into a `requirements` area,
   `security.auth` into an `auth` area; drop the review mode and thresholds,
   `testing.run`, `testing.mutants` and each `proven_hash`. Then run
   `bin/alpha answers check` until it prints ok.
3. Run `bin/alpha apply <project>`: alpha's own files are replaced, and every
   other file of alpha's that differs becomes a proposal to merge by hand.
   Then `bin/alpha bootstrap <project>` and `bin/alpha commit <project>`.

## Develop

```sh
git clone https://github.com/vs/alpha ~/workspace/alpha
claude --plugin-dir ~/workspace/alpha   # this checkout, for this session only
mise install && mise run check   # every check the kit runs on itself
uv run pytest -m slow   # also bootstraps real projects; needs uv, pnpm, network
```

## Setup and test

### alpha (`./`)

```sh
uv sync
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before your first commit.

Design: [docs/superpowers/specs/2026-10-19-project-kit-design.md](docs/superpowers/specs/2026-10-19-project-kit-design.md)
