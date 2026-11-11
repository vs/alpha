# alpha

[![Claude Code plugin](https://img.shields.io/badge/Claude_Code-plugin-D97757?logo=claude&logoColor=white)](https://code.claude.com/docs/en/plugins)
[![Python recipe](https://img.shields.io/badge/recipe-Python-3776AB?logo=python&logoColor=white)](recipes/python.toml)
[![TypeScript recipe](https://img.shields.io/badge/recipe-TypeScript-3178C6?logo=typescript&logoColor=white)](recipes/typescript.toml)
[![Rust recipe](https://img.shields.io/badge/recipe-Rust-B7410E?logo=rust&logoColor=white)](recipes/rust.toml)
[![Any stack](https://img.shields.io/badge/recipe-any_stack-555)](skills/stack-recipe/SKILL.md)

alpha interviews you about a new project, then writes what agents build on:
principles, docs, decision records, Claude Code and git hooks, CI, and a test
setup per component that passes from the first commit. It writes no app code.
Each principle is checked, by a hook or by a reviewer agent that blocks
"done".

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
| `.claude/` | permissions, hooks, the principles reviewer, a commit skill |
| each component | strict lint, types and tests, wired up with no `src/` |
| `mise.toml` | the repository checks, tools pinned: `mise run ci` runs them (secrets, typos, markdown, links, action pins, agent config) |
| `.github/` | CI running the same checks, a weekly scheduled run, Dependabot |

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

When you override a default, alpha asks whether to keep it for your next
projects. A yes goes to `~/.config/alpha/overrides.toml`, a recipe drafted in
an interview to `~/.config/alpha/recipes/`. Both apply on top of the installed
plugin and survive its updates.

## Develop

```sh
git clone https://github.com/vs/alpha ~/workspace/alpha
claude --plugin-dir ~/workspace/alpha   # this checkout, for this session only
uv run pytest
uv run ruff check && uv run pyright
bin/alpha-evals run   # real interviews; spends tokens
```

Design: [docs/superpowers/specs/2026-10-19-project-kit-design.md](docs/superpowers/specs/2026-10-19-project-kit-design.md)
