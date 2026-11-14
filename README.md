# alpha

[![Claude Code plugin](https://img.shields.io/badge/Claude_Code-plugin-D97757?logo=claude&logoColor=white)](https://code.claude.com/docs/en/plugins)
[![Python recipe](https://img.shields.io/badge/recipe-Python-3776AB?logo=python&logoColor=white)](recipes/python.toml)
[![TypeScript recipe](https://img.shields.io/badge/recipe-TypeScript-3178C6?logo=typescript&logoColor=white)](recipes/typescript.toml)
[![Rust recipe](https://img.shields.io/badge/recipe-Rust-B7410E?logo=rust&logoColor=white)](recipes/rust.toml)
[![Any stack](https://img.shields.io/badge/recipe-any_stack-555)](skills/stack-recipe/SKILL.md)

alpha interviews you about a new project, then writes what agents build on:
principles, docs, decision records, Claude Code and git hooks, CI, and a test
setup per component that passes from the first commit. It writes no app code.
Each principle is checked, by a hook or by a reviewer agent that must pass
before a change reaches main.

```sh
claude plugin marketplace add vs/alpha
claude plugin install alpha@alpha
```

```text
/alpha:new-project ~/code/my-app
```

## What you get

| | |
|---|---|
| `docs/principles.toml` | the one file CLAUDE.md, hooks and reviewer read |
| `docs/decisions/` | a record per interview area and per override |
| `.claude/` | permissions, hooks, the principles reviewer, skills to commit, record a decision, and review a change, the whole repo or its `shortcut:` ledger |
| each component | strict lint, types and tests, wired up with no `src/` |
| `mise.toml` | the repository checks, tools pinned: `mise run ci` runs them (secrets, typos, markdown, links, action pins, agent config) |
| `.github/` | CI running the same checks, a weekly scheduled run, Dependabot |
| `docs/design-language.md` | optional: one look for every visual, from diagrams in the docs to the UI, which the reviewer holds each changed visual to |

The design language is yours to skip. Define it in the interview (character,
palette, typography, shape, imagery, diagram style) and it becomes a principle
that CLAUDE.md states, and the source of the UI's tokens. Skip it, and alpha
enforces and recommends nothing about how visuals look. `/alpha:extend define a
design language` adds one later. Which files count as visuals is the `[visuals]`
list in `docs/principles.toml` (diagram sources, SVG, styles, tokens, chart
specs; docs and UI markup when a change touches something visual; images and
fonts are named but can't be read). The interview asks for the paths of
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
/alpha:adopt ~/code/old-service
```

alpha surveys the repo and interviews you with what it already does as the
recommendations. Then it installs the same enforcement on a branch,
`alpha/adopt`, keeping the repo's own tools where they meet the principles.
Today's lint, type, test and docs findings are baselined, so only new ones
fail, and a baseline only shrinks. What's left is a compliance plan in
`docs/adoption.md`: run `/alpha:adopt` again to work through it one step at a
time, each step done only when its check passes.

## Change it later

```text
/alpha:extend add a worker component
```

It asks again only what the change affects, and merges into files you edited.

## Update

```sh
claude plugin marketplace update alpha
claude plugin update alpha@alpha
```

Your projects move to the new kit with the plugin's `bin/alpha update
<project>` (try `--dry-run` first), then `bin/alpha commit-update <project>`;
Claude finds `bin/alpha` for you if you ask it to update the project to the
new alpha. alpha merges its
newer hooks, checks and files into yours and keeps your edits; where they
overlap, it leaves a proposal for you to merge by hand.

When you override a default, alpha asks whether to keep it for your next
projects. A yes goes to `~/.config/alpha/overrides.toml`, a recipe drafted in
an interview to `~/.config/alpha/recipes/`. Both apply on top of the installed
plugin and survive its updates.

## Develop

```sh
git clone https://github.com/vs/alpha ~/workspace/alpha
claude --plugin-dir ~/workspace/alpha   # this checkout, for this session only
mise install && mise run check   # every check the kit runs on itself
uv run pytest -m slow   # also bootstraps real projects; needs uv, pnpm, network
bin/alpha-evals run   # real interviews; spends tokens
```

## Setup and test

### alpha (`./`)

```sh
uv sync
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before your first commit.

Design: [docs/superpowers/specs/2026-10-19-project-kit-design.md](docs/superpowers/specs/2026-10-19-project-kit-design.md)
