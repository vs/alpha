# alpha

[![Claude Code plugin](https://img.shields.io/badge/Claude_Code-plugin-D97757?logo=claude&logoColor=white)](https://code.claude.com/docs/en/plugins)
[![Python recipe](https://img.shields.io/badge/recipe-Python-3776AB?logo=python&logoColor=white)](recipes/python.toml)
[![TypeScript recipe](https://img.shields.io/badge/recipe-TypeScript-3178C6?logo=typescript&logoColor=white)](recipes/typescript.toml)
[![Rust recipe](https://img.shields.io/badge/recipe-Rust-B7410E?logo=rust&logoColor=white)](recipes/rust.toml)
[![Any stack](https://img.shields.io/badge/recipe-any_stack-555)](skills/stack-recipe/SKILL.md)

alpha puts a development process into a project for Claude Code to work
under: principles, docs, Claude Code and git hooks, CI, and a test setup per
component that passes from the first commit. It writes no app code. Each
principle is checked, by a hook or by a reviewer agent that must pass before
a change reaches main.

```sh
claude plugin marketplace add vs/alpha
claude plugin install alpha@alpha
```

```text
/alpha:install ~/code/my-app
```

In an empty folder, alpha interviews you and sets up a new project. In a repo
that has code, it adopts it on a branch. Where its hooks were switched off, it
switches them back on.

The interview asks only what alpha needs to set up the process: the name,
license, components and stacks, tests, docs, CI, releases, git and secrets.
It asks one question at a time, each with a recommended answer: a choice in
Claude Code's question dialog, the recommendation first; a draft, such as the
project's name, as text ending in the recommended answer, for you to confirm
or rewrite. Then it offers each part of the product (requirements,
performance, UI and the rest) one at a time, skipped unless you already know
it; what you skip stays open until you ask.

## What you get

| | |
|---|---|
| `CONTRIBUTING.md` | how the project is set up, checked, committed, built, released and kept secure |
| `CLAUDE.md`, `README.md` | the rules Claude follows, and how to set up, test and run each component |
| `docs/alpha/principles.toml` | the one file CLAUDE.md, the hooks and the reviewer read |
| `docs/alpha/specification.md` | what the product does: the parts settled so far, the rest listed as open, each with the request that settles it |
| `docs/alpha/features/`, `bug-fixes/`, `refactorings/`, `perf/` | a folder per full-track task (`/alpha:brainstorm`): its research, spec and plan |
| `.claude/` | permissions, hooks, the principles reviewer, and skills to commit, record a decision in the docs, and review a change or the whole repo |
| each component | strict lint, types and tests, wired up with no `src/`; a monorepo's Rust components form one Cargo workspace at the root |
| `mise.toml` | the repository checks, tools pinned: `mise run ci` runs them (secrets, vulnerabilities, typos, markdown, links, action pins, agent config) |
| `.github/` | CI running the same checks, a weekly scheduled run, Dependabot |

In a repo that already has a doc alpha would write (an architecture page, a
glossary, a dependency log), alpha's file links to yours instead of repeating
it. It never overwrites a file of yours.

## What is checked, and when

- **On every edit:** the file is formatted and linted.
- **When Claude stops:** no secret added, source changed with its tests (or a
  reason it needs none), mapped docs updated with their code, a dependency
  recorded with its reason, no migration edited after the fact, and the type
  and structure checks of each changed component green.
- **On every commit, by anyone:** the commit convention, through git's
  `commit-msg` hook.
- **Before work reaches main** (a push to main, or merging a pull request):
  each changed component's full test suite, and the principles reviewer. The
  reviewer runs once there, on what changed since its last review, never at
  Stop or after a task. Its result is a git note on the tree it reviewed,
  which stays in your clone. When it finds problems, the next review only
  checks those and what's new; Claude may accept a finding it disproves with
  an `Accepts:` trailer, but a finding on a risky path needs you to reply
  `accept F-…`.
- **In CI:** every component's checks, and a pull request fails when its tests
  leave too much of the changed lines uncovered.

## Settle the product

```text
/alpha:update let's settle requirements and performance
```

The product's parts (requirements, architecture, errors, design language, UI,
accessibility, observability, data, performance, auth) start open: you often
can't know them on day one. `/alpha:update` settles the ones you name. It
reads what your code and docs already say, offers two or three options with
their trade-offs, asks you to choose, then writes the section and switches on
the principles it gates.

The design language is yours to skip. Settled, it becomes a principle CLAUDE.md
states and the source of the UI's tokens, and the reviewer holds each changed
visual to it. It guides; it isn't a wall: a visual may step outside it for a
stated reason, and only drift is a finding. You choose how firmly colors are
held: `advise` (the default) shows the reviewer each color outside the
palette, `enforce` adds a `palette` check that fails on one, `off` does
neither.

## Exhaustive testing, if you ask

For a project that must not fail, say yes to exhaustive testing in the
interview (or later: `/alpha:update test this exhaustively`). alpha adds a
principle modeled on [how SQLite is tested](https://www.sqlite.org/testing.html):
every branch taken both ways, every failure forced by injecting it, fuzz or
property-based tests for outside input, limits tested on both sides, a
failing test before each bug fix, invariants asserted in the code. The
reviewer holds every change to it, and CI fails a pull request that leaves a
changed line or branch uncovered. It is off by default. Rust coverage records
branches too: only the coverage run uses a pinned, dated nightly, since stable
Rust reports none.

## Needs

Python 3.11 or newer as `python3`, which runs alpha itself: on an older one
it stops and says how to get a newer one (macOS ships 3.9). Then
[uv](https://docs.astral.sh/uv/) and [pnpm](https://pnpm.io/) for the Python
and TypeScript components, [rustup](https://rustup.rs/) for Rust ones, and
[mise](https://mise.jdx.dev/) to install and run the repository checks. A
component on another stack (Go, say) needs its own toolchain; alpha drafts a
recipe for it with you and proves it before it writes anything.

## Bring an existing repo in

```text
/alpha:install ~/code/old-service
```

The repo must be a git repository with its work committed. alpha surveys it
and interviews you with what it already does as the recommendations. Then it
installs the same enforcement on a branch, `alpha/adopt`, keeping the repo's
own tools where they meet the principles; a file the repo already has becomes
a proposal you merge, never an overwrite. A part that has docs but no build
files yet gets the skeleton a new project would, after one question. Today's
lint, type, test and docs findings are baselined, so only new ones fail, and a
baseline only shrinks. What's left is a compliance plan in
`docs/alpha/adoption.md`: run `/alpha:install` again to work through it one
step at a time, each step done only when its check passes.

## Work in it

```text
/alpha:do add CSV export to the report command
```

alpha picks a playbook for the task (investigation, feature, bug fix,
refactoring, perf, prototype, session pickup or pause) and follows it step by
step, keeping the project's principles, docs and checks. This is the light
track: straight into the work, with a short design said in chat and no spec
files. Tests are written first and fail before the code makes them pass. A
part of the product the task needs that is still open is named with its
`/alpha:update <area>` request.

```text
/alpha:brainstorm add CSV export to the report command
```

The full track, for a feature, bug fix, refactoring or perf task you want
thought through first. `/alpha:brainstorm` researches the code and how other
projects solve it, brainstorms with you one question at a time, and writes a
spec that names a test for each acceptance check, in a folder named by the
playbook: `docs/alpha/features/`, `bug-fixes/`, `refactorings/` or `perf/`.
Once you approve it, `/alpha:plan` writes the plan and asks how to build it:
native, where Claude builds every task, or with subagents, where a fresh one
builds each task and another reviews it. Then `/alpha:execute` builds it
without stopping to check in, keeps a ledger it resumes from, lists every
call it made on your behalf, and runs the principles review once at the end.

## Change it later

```text
/alpha:update add a worker component
```

With a request, `/alpha:update` changes a component or a setup answer, or
settles a product area. It asks again only what the change affects, and
merges into files you edited.

## Decisions live in the docs

A project keeps no decision records. A choice changes the doc it governs:
what the product does in `docs/alpha/specification.md`, how the work is done
in `CONTRIBUTING.md`, a loosened principle as an override listed there, an
exception to a check as a row of its Exceptions table, and an accepted review
finding as an `Accepts:` trailer on a commit. Git history keeps when and why.

## Update

```sh
claude plugin marketplace update alpha
claude plugin update alpha@alpha
```

Then run `/alpha:update`, with no request, in each project. alpha merges its
newer hooks, checks and files into yours against the version it last wrote,
which it keeps in git objects, never in a file of yours. Your edits stay; where they overlap
alpha's change, it leaves a proposal, and the skill merges it with you.

When you override a default, alpha asks whether to keep it for your next
projects. A yes goes to `~/.config/alpha/overrides.toml`, a recipe drafted in
an interview to `~/.config/alpha/recipes/`. Both apply on top of the installed
plugin and survive its updates.

## Switch it off, or remove it

`/alpha:uninstall` is the one way to switch alpha's hooks off: it takes
alpha's hook entries out of `.claude/settings.json` and its commit-msg hook
out of git (`core.hooksPath`, or the call between `# alpha:begin` and
`# alpha:end` in your own hook manager's file). It deletes no file and commits
nothing; `/alpha:install` switches the hooks back on as they were.

`/alpha:purge` removes alpha altogether, in one commit: it uninstalls the
hooks, deletes `.claude/alpha/`, `docs/alpha/` and alpha's agents and skills
(even edited ones), and takes out only what points at them from the files you
keep: lines in `CLAUDE.md`, `CONTRIBUTING.md` and `README.md`, alpha's entries
in `.claude/settings.json`, the tool configs, `.gitignore`, and the `mise.toml`
tasks that ran alpha's scripts; the secrets check stays, running the same scan
without alpha's script. Your components' scaffolding stays, so the project
still builds and tests. A file it can't clean stops it before it
writes anything, naming the line to fix. Claude runs neither unless you ask.

## Projects an older alpha set up

An alpha before 1.0 kept a `manifest` in `.claude/alpha/project.json`; this
alpha doesn't upgrade such a project on its own. By hand, in one sitting:

1. Move `docs/principles.toml` and `docs/dependencies.md` into `docs/alpha/`,
   and fold `docs/specification.md`, `docs/glossary.md`,
   `docs/design-language.md` and `docs/adoption.md` into `docs/alpha/`; old
   feature specs in `docs/specs/` go to `docs/alpha/features/`.
2. Replace `manifest` in `project.json` with an `installed` record read from
   it: `kit_version` its kit version; `mode` `"adopted"` when it has
   `adopted_at`, else `"new"`; `on` that date (else `generated_at`);
   `components` its `added`; and `preexisting` the files alpha writes that
   the repo had when the adoption surveyed it (`git ls-tree -r --name-only`
   at the survey's `git.head`), or `[]` for a project alpha generated.
   Reshape the answers: identity's target users and requirements go into a
   `requirements` area, `security.auth` into an `auth` area; drop the review
   mode and thresholds, `testing.run`, `testing.mutants`, each `proven_hash`,
   the `decisions` list and each adoption step's `decision`, after moving any
   rule still in force from them or from `docs/decisions/` into `docs/alpha/`
   or `CONTRIBUTING.md`. Then run `bin/alpha answers check` until it prints ok, and
   `bin/alpha recipe try` for each drafted recipe. Commit steps 1 and 2:
   `apply` merges only into committed files.
3. Run `bin/alpha apply <project>`: alpha's own files and hook entries are
   replaced, and every other file of alpha's that differs becomes a proposal
   to merge by hand. Then `bin/alpha bootstrap <project>` and
   `bin/alpha commit <project>`.
4. In a repo whose own hook manager calls alpha's commit check, put
   `# alpha:begin` and `# alpha:end` lines around that call.

## Develop

```sh
git clone https://github.com/vs/alpha ~/workspace/alpha
claude --plugin-dir ~/workspace/alpha   # this checkout, for this session only
mise install && mise run check   # Python, uv, the tools; every check
uv run pytest -m slow   # real projects; needs pnpm, mise, cargo, network
```

What alpha does, in full: [docs/specification.md](docs/specification.md)

## Setup, test and run

### alpha (`./`)

```sh
cd .
uv sync
uv run pytest
bin/alpha --help
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before your first commit.
