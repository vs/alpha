# Project kit: design

Date: 2026-10-19
Status: approved, and built as of alpha 0.8.0 (2026-11-14). §15 lists what
waits for a later version.

Name: **alpha**, the same as this repo. "Alpha" is the first letter and the first version: where every project starts. Skills are invoked as `/alpha:<skill>` (e.g. `/alpha:new-project`).

## 1. Intent

Starting a new project with Claude Code today means rebuilding the same
foundation by hand each time: the CLAUDE.md, the permissions, the hooks, the
test runner, the docs layout, the commit rules, and above all the *principles*
the agents are supposed to follow. Some of it gets forgotten. What does get set
up is enforced only by hope.

The kit fixes that. It is a Claude Code plugin that:

1. **Interviews the user** about a new project in the style of Matt Pocock's
   `grill-me`. It works the decisions as a tree, asks in rounds, and
   recommends an answer for every question. It doesn't stop until no branch
   is left silently assumed.
2. **Writes a skeleton** into an empty folder. The skeleton holds no app code:
   only the ground agents build on. That's the principles, the docs, the
   Claude Code settings and hooks, and a wired-up test setup per component.
3. **Keeps agents honest afterward.** Cheap mechanical checks run on every
   edit and commit. A judgment-based reviewer checks batched changes against
   the project's own principles.

The user's own opinions about how software should be built are the product.
The kit proposes them as defaults, the user confirms or overrides them per
project, and the kit's defaults improve from project to project, with the
user's consent each time.

## 2. Goals, non-goals, anti-goals

**Goals**
- One entry point ("start a new project") that takes an empty folder to a
  committed, enforced skeleton.
- One skill per area (testing, UI/UX, builds, and so on) that the entry
  point calls in turn and that can be called directly later in a project's
  life.
- One principles file per project, the single source of truth that CLAUDE.md,
  the hooks, and the reviewer all read.
- Works for multi-component apps (backend, frontend, CLI, mobile, ML pipeline),
  where each component may use a different stack.
- First-class recipes for **Python** (ML), **TypeScript** (web apps) and
  **Rust**. Any other stack still works, set up from that stack's usual
  conventions and marked as less proven.

**Non-goals (v1)**
- No app code, not even a hello-world. The skeleton is configuration, docs,
  test wiring, and enforcement only.
- No existing projects in `new-project`. It runs only on empty folders.
  **Exceptions (user decisions):** area skills may be called directly on a
  project *the kit generated* to extend it (see §5a); they never touch app
  code. And `adopt` (2026-11-11) brings an existing repo under the kit with
  a compliance plan whose steps Claude carries out one by one (see §5b).
- No infrastructure provisioning. Hosting is decided and documented, and
  CI is configured, but cloud resources are not created.

**Anti-goals: failures even if it technically works**
- **Skipping areas to save time.** The kit is thorough and consistent. If the
  user stops partway, that's their call; the kit never shortcuts an area on its
  own. It must be resumable.
- **Principles that only live in prose.** A principle with no check behind it
  (mechanical or reviewer) is a wish. Every principle names how it's checked.
- **Principles scattered across files.** Changing a threshold in one place
  must change behavior everywhere.
- **Ceremony on small projects.** Principles that don't fit a weekend CLI must
  switch off through their when-it-applies condition, not weigh it down.
- **Silently changing kit defaults or existing projects.** Defaults change only
  when the user says yes. Projects never pick up new kit defaults unless asked.
- **Agents weakening checks to pass them.**

## 3. The shape

A Claude Code plugin, developed in this repo and installed from GitHub
(`vs/alpha`) once, then used everywhere.

| Part | What it is |
|---|---|
| `new-project` skill | User-invoked entry point. Runs the interview across all areas, then generates the skeleton. Resumable. |
| `adopt` skill | User-invoked entry point for an existing repo. Surveys it, runs the interview with the repo's practice as the recommendations, installs the enforcement with baselines for legacy debt, and writes a compliance plan it then carries out step by step (§5b). Resumable. |
| `grilling` skill | Shared interview primitive used by `new-project` and every area skill (design tree, rounds, recommended answers; see §4). |
| Area skills | One per area in §5. Each owns its questions, its principles, and the files it writes. Callable by `new-project` and directly. |
| Stack recipes | Per-stack data and templates: test runner, linter/formatter, type checker, commands, permission lists, and stack rules. Full for Python, TypeScript and Rust, generic fallback for others. |
| `registry/` | The repo-check tool registry (§8a): one entry per tool, with its pinned version and the command that runs it. |
| Hook scripts | The mechanical checks in §8. Shipped by the kit, wired into each project's `.claude/settings.json` and git hooks. |
| `principles-reviewer` agent | The judgment-based reviewer in §9. |
| `commit` skill + `committer` agent | Ported from the user's `~/.claude/commands/commit.md` and `~/.claude/agents/committer.md` (see §10). |
| Kit defaults | The user's default principles, thresholds, and preferred answers, with a change history (see §11). |

## 4. The interview

Modeled on `mattpocock/skills` → `grilling`:

- Decisions form a **design tree**. The **frontier** is every decision whose
  prerequisites are settled. Each round asks the whole frontier, numbered, each
  question with a **recommended answer** worded so "yes" accepts it.
  Recommendations come from the kit defaults. A round is compact plain text
  (user decision, 2026-11-11): a bold numbered title and the question, an
  optional `Options:` line, a `Recommended:` line, and no emoji, rules or
  background the user didn't ask for.
- **Facts are the kit's job, decisions are the user's.** Never ask what can be
  looked up (installed tool versions, whether `gh` is authenticated, the latest
  stable version of a framework).
- **Decisions are recorded as they're made**, as decision records under
  `docs/decisions/` (ADR-style), not reconstructed at the end. My call on
  granularity, to avoid 100+ files: **one record per area** summarizing its
  decisions, plus **a separate record for each override** of a kit default
  and for each decision made later in the project's life. Each record says
  its `Kind`: `product` (identity, design language, UI, accessibility: what
  the product does and for whom) or `technical` (the rest). Claude may supersede a technical
  record with a recorded reason; a product record, or one that changes a
  principle, needs the user's agreement, which the reviewer checks.
- **Done** means the frontier is empty and the user confirms shared
  understanding. Only then are files generated.
- **Resumable:** interview state is persisted in the target folder, so
  re-running `new-project` picks up where it left off.
- **Overrides:** whenever the user overrides a kit default, the kit records it
  in the project's decision log *and* asks: "Make this the default for future
  projects too?" (§11).

Order: identity, then components and stacks, then the remaining areas. Every
later area applies to every component.

## 5. Areas

Each area skill owns its questions, the principles it contributes (§6), and the
files it writes (§7). The lists below are what each area must settle at
minimum. The exact question wording is the builder's.

1. **Identity.** Name, value proposition, target users, technical requirements
   (turned into a short list of *acceptance checks* that tests later trace
   back to), license, contributor guide.
2. **Components & stack.** Which components exist (backend, frontend, CLI,
   mobile, ML pipeline, library, …). Per component: language, framework,
   package manager, test runner, linter/formatter, type checker. Repo layout
   (single package or monorepo). Suggest a stack from the component type (ML →
   Python + uv + pytest + ruff + pyright; web → TypeScript + the user's chosen
   framework + Vitest + ESLint/Prettier or Biome). The tool picks are the
   builder's to finalize per recipe. A stack's rules for code are enforced
   by its linter and compiler settings wherever a tool can check them; the
   recipe lists the rest as **stack rules**, which go into CLAUDE.md under
   the components on that stack and are checked by the reviewer (§9).
3. **Architecture.** Simplest design that solves the problem. Component
   boundaries and contracts between components.
4. **Errors.** Detect early. Every user-facing error says what went wrong *and*
   how to fix it. Error taxonomy and format per component.
5. **Testing.** Test effort matches core-logic effort. Test layout per
   component, which test levels apply (unit, integration, end-to-end, contract),
   how acceptance checks map to tests, and whether the project opts into
   exhaustive testing (§6).
6. **Design language** (optional; user decision, 2026-11-13). The one look
   every visual of the project follows, from the diagrams in its docs to its
   UI: character, palette, typography, shape, icons and imagery, and how
   diagrams and charts are drawn. The area's first question is whether to
   define one, and skipping is a full answer: then the kit writes nothing
   about visuals, and enforces and recommends nothing. Defined, it becomes
   `docs/design-language.md`, the "One design language" principle (§6),
   which CLAUDE.md states in one line that names the page, and the source the
   UI area's tokens, typography and icons come from. Which files count as visuals is a list in the kit
   defaults (`[design_language.visuals]`): `sources` that are always visuals
   (diagram sources, SVG, styles, tokens, chart specs), `carriers` that count
   only when a change touches a diagram block, a style or a color (docs, UI
   markup), `opaque` ones (rasters, fonts, design-tool files), and exclusions
   for third-party and generated files, to which the interview adds the
   project's own third-party paths. The project gets it as `[visuals]` in its
   principles file, and the reviewer's brief names the changed files on it.
   The design language guides and isn't a wall (user decision, 2026-11-13):
   a visual may step outside it for a stated reason, and only drift is a
   finding. How firmly colors are held is an answer, `palette_check`:
   `advise` (default) shows the reviewer each color outside the palette in
   diagrams, SVG and stylesheets to judge; `enforce` adds the `palette`
   repository check (§8a), which fails on one; `off` does neither. The check
   reads hex, rgb() and hsl() only, ignores alpha and rounding, and lets
   black, white, named colors and variables pass. Answers saved before the
   kit had this area read as skipped, so older projects stay as they are.
7. **UI/UX** (only if a component has a UI). The set of visual tools that
   make up the UI: design tokens, component library, icon set, typography,
   theming, plus visual regression and accessibility checks.
8. **Documentation.** Internal vs external docs, where external docs live, and
   how they're kept in step with code (which code paths map to which docs, for
   the docs-drift check).
9. **Build, CI, hosting.** How each component is built, the CI provider and
   what it runs, where each component is hosted, environments.
10. **Security & secrets.** Where secrets live, what's never committed,
    auth approach if any, protected paths.
11. **Dependencies.** Policy for adding, pinning, and upgrading. Lockfiles. A
    dependency log entry with the reason for each new dependency.
12. **Observability.** Logging format (structured), levels, correlation across
    components, metrics or tracing if needed.
13. **Versioning & releases.** Versioning scheme, changelog, release process.
14. **Data & migrations** (only if there's persisted data). Storage, schema
    ownership, migration tool and rules. For ML: data versioning, seeds,
    experiment tracking.
15. **Accessibility** (only with a UI). Target level, automated checks.
16. **Performance.** Budgets per component (response time, bundle size,
    memory, training/inference time) and how they're measured.
17. **Git history.** Commit convention and scopes (per component), branching
    model, what's protected (§10).
18. **Agent workflow.** Hooks, permissions, review thresholds and risk
    triggers (§9), definition of done.

## 5a. Calling an area skill on a kit-generated project

User decision: in v1, area skills work on projects the kit generated (they
recognize them by the kit metadata), not only during the first interview.
Typical uses: add a component (e.g. a UI to a project that started as a CLI),
switch on an area that didn't apply before, or revisit an area's decisions.

- Re-interview only that area (plus anything it unlocks, e.g. a new UI
  component unlocks the UI/UX and accessibility areas), with the project's
  current answers as the recommended defaults.
- **Merge** into the kit-owned files (principles file, CLAUDE.md, docs,
  settings, hooks, configs). **Never overwrite the user's edits.** Show the
  proposed changes and confirm before writing.
- Record a decision record for the change, and commit per the convention.
- Never create or modify app code. Wiring a new component's test runner and
  configs is in scope; writing its code is not.
- On a folder the kit didn't generate or adopt, refuse and point to `adopt`
  (§5b).
- **Kit upgrades** (decision 0022). When the manifest's `kit_version` is
  older than the running alpha, `alpha update` also brings the project to
  this kit, copied files (hooks, checks, skills, agents, the git hook)
  included. The base of each three-way merge is what the older kit wrote,
  rendered by that kit's own code from the answers it set the project up
  from; alpha finds it in the manifest's kit folder, the recorded commit of
  a checkout, the plugin cache, or this checkout's `v<version>` tag, and
  stops with where to put it otherwise. A project from a newer alpha is
  refused.

## 5b. Adopting an existing project

User decision (2026-11-11): `/alpha:adopt [folder]` brings a repo the kit
didn't generate under the kit. The result is the same enforced project a
generated one gets, plus a **compliance plan** that brings the existing code
up to the principles over time. The plan may rework components.

**Decisions (user):**

- **A1 Keep tools that meet the principle.** When the repo already uses a
  tool that can enforce a principle (mypy strict, ESLint, jest, poetry), the
  kit keeps it: Claude drafts a project-local **adopted recipe** from the
  repo's real commands and proves it on a throwaway worktree of the repo.
  Moving to the kit's own tool is an optional plan step, never forced.
- **A2 Baseline and ratchet.** Today's violations are recorded as a
  baseline; the checks fail only on new ones, and the baseline only shrinks
  (§8b). Legacy debt never blocks normal work, and never grows unnoticed.
- **A3 Claude carries out the plan, one step at a time.** The plan is
  committed. Each run of `/alpha:adopt` in an adopted project picks the next
  ready step and does it on its own branch, under the project's own hooks
  and reviewer. A step is done only when its acceptance command passes.
  The kit's CLI still writes only the kit's files; rework of app code is
  ordinary work by Claude.

**The flow.** Each step shows its result before the next one writes
anything.

1. **Survey (facts, no questions).** Components (from the manifests a
   recipe's `[detect]` table names), stacks, the tools in use and how strict
   they are, the commands that already run (CI, task runners, scripts),
   docs and decision records already there, license, CI provider, git hook
   managers, migration folders, test layout, and how many recent commits
   follow the convention. The survey is kept in the interview state.
2. **Interview: all areas, in §4's order.** Recommendations come from the
   survey where the repo's practice meets the principle, and from the kit
   defaults otherwise. Nothing the repo already answers is asked. Wherever
   the repo falls short of an active principle, a **gap** is recorded. A
   component the docs describe whose folder is missing or holds only docs
   has no tools to adopt: the user is asked once whether the kit generates
   its skeleton, and on yes it takes the kit's recipe (or a drafted one), as
   in a new project (decision 0030).
3. **Assessment.** The audit's lenses (§9, on-demand reports), run per
   active principle over the whole repo, find gaps no tool reports: the
   error format, validation at the edges, contracts, config from the
   environment, timeouts, logs, acceptance checks with no test.
4. **Preview.** Before anything is written: the kit files to add, the
   files to merge (with diffs and conflicts), the baselines to capture
   (counts per check, component and rule), and the plan's steps. The user
   confirms.
5. **Install, on branch `alpha/adopt`.** The kit's files are merged in with
   the three-way merge of §5a. The "before" side is empty, so a file the
   repo already has is merged by hand, keeping the user's side. `.gitignore`
   and `.claude/settings.json` are merged mechanically, the existing LICENSE
   is kept, and component templates are never written over an existing
   manifest. A component on a kit or drafted recipe with no manifest in its
   folder gets that recipe's skeleton, bootstrapped and committed whole as
   in a new project. New decision records are numbered after any already in
   `docs/decisions/`. Then the baselines are captured, the components are
   bootstrapped green under them, and the result is committed in the
   convention's groups. The user opens the pull request.
6. **The plan.** `docs/adoption.md` (rendered from the interview state)
   lists the steps by phase. Each step names the principles it serves, why
   it's needed, an acceptance command, and the steps it depends on.

| Phase | What its steps do |
|---|---|
| P0 Urgent | Secrets found in the repo: rotate them. Only the user marks these done. |
| P1 Normalize | One formatting commit per component, listed in `.git-blame-ignore-revs`; lockfiles and pins. |
| P2 Close tool gaps | Add a missing type checker, test runner or coverage; tighten configs to the principle's strictness, each with its own baseline. |
| P3 Optional migrations | Move a component to the kit's tool. Offered, not recommended by default. |
| P4 Rework | Fix the assessment's gaps: contracts, error format, config from the environment, timeouts, logs, migrations. |
| P5 Burn-down | Bring each baseline to zero per component and rule, risk paths first. The last step removes the baseline. |
| P6 Traceability | Link the product brief's acceptance checks to tests. |

A step may be **dropped** only with a decision record that says why. That
is a loosening, so it needs the user's agreement (§4).

**Git hooks.** When the repo already has a hook manager or a
`core.hooksPath`, the kit doesn't take the hooks path over: its
`commit-msg` check chains to the existing hooks instead. The convention
binds only new commits; existing history is never rewritten.

**Refusals.** Each refusal says what to do next: the folder isn't a git
repository; the working tree has uncommitted changes; the kit already
generated or adopted the folder (use `extend`).

After adoption, the project is a kit project like any other: `extend` and
`alpha update` work on it, and §11 still holds. Adoption opts a project into
the kit's gates as they are on the day it's adopted; later kit versions
reach it through `alpha update` (§5a).

## 6. The principles catalog

Kit defaults, all kept, each with a when-it-applies condition. ★ = always on.
The interview may tune conditions and thresholds per project. A component may
**tighten** a principle. **Loosening or dropping** one for a project or
component requires an explicit decision record.

Each principle in the project's principles file carries: id, statement,
rationale, when-it-applies, how it's checked (mechanical hook, reviewer, or
both), and any parameters.

**User's core principles**
- ★ **Simplest sufficient architecture.** As simple as possible, as complex as
  the problem requires.
- ★ **Fail fast, fail helpfully.** Detect errors as early as possible. Every
  error message describes the problem and tells the user how to proceed.
- ★ **Tests are as important as the core.** Test design and writing get the
  same effort and intensity as the logic. Tests trace back to acceptance
  checks.
- **Exhaustive testing.** *When: the project opts in (`testing.exhaustive`;
  user decision, 2026-11-13).* Modeled on
  [SQLite's testing](https://www.sqlite.org/testing.html): every branch taken both
  ways, every failure path forced by an injected failure, fuzz or
  property-based tests for whatever reads outside input, each limit tested
  at, just below and just above its value, a failing test before each bug
  fix, invariants asserted in the code, and tests run on the build that
  ships. Off by default (`defaults.testing.exhaustive`), since it takes
  several times more test code than product code. The reviewer checks it,
  and the diff-coverage gate (§8a) becomes every changed line and branch.
  The fuzzing and property-testing tools aren't picked by the recipes; a
  project adds each when its first test needs it. Mutation testing is gated
  where the recipe has a `mutants` command (Rust: cargo-mutants, decision
  0029; §8a).
- **A deliberate visual system.** *When: a component has a UI.* The UI is
  built from the declared set of visual tools, not ad-hoc styles.
- **One design language.** *When: the user defined a design language.* Every
  visual the project makes (a diagram, a chart, an image, the UI) is built
  from it. A visual may step outside it for a stated reason; it may not
  drift from it. The reviewer checks each changed visual it can read as text
  against `docs/design-language.md`, a change to that page is a risk path,
  and the `palette` check holds colors when the project chose `enforce`.
- ★ **Docs move with the code.** A change to public behavior updates the docs
  in the same change.
- ★ **Build and hosting are decided up front** and runnable in CI.

**Code shape**
- ★ **Validate at the edges, trust the inside.** External input is parsed into
  typed data once, at the boundary. Inside, code doesn't re-check what its own
  modules return; each remaining cast or runtime check says which boundary or
  invariant it serves.
- ★ **Strict types.** TypeScript `strict`, Python type-checked in strict mode.
- **Logic in the middle, side effects at the edges.** *When: the component has
  non-trivial business logic.*
- ★ **No dead code.** No commented-out code, no speculative options.
- ★ **Code over comments.** A comment stays only for what the code can't
  say: a license header, a rule set by a dependency, platform or protocol we
  can't change, a public API's contract, or an issue link for a constraint.
  Anything surprising in our own code is fixed by renaming, extracting or
  retyping it until it reads plainly, not explained in prose.
- ★ **Generated files come from their source.** A generated file changes only
  by changing its source and regenerating it, never by hand.

**Between components**
- **Contracts are the source of truth.** *When: ≥2 components talk to each
  other.* Interfaces defined once (OpenAPI/JSON Schema/protobuf). Clients and
  checks are generated from them.
- **One vocabulary.** *When: ≥2 components, or a domain with its own jargon.*
  A glossary, and consistent names across code, docs, and UI.

**Running it**
- ★ **One command each to set up, test, and run**, per component, on a fresh
  machine.
- ★ **Reproducible.** Pinned dependencies and lockfiles. *For ML:* seeds,
  data versions, recorded experiment configs.
- **Config from the environment.** *When: the component is deployed.*
- **Every external call has a timeout and a failure path.** *When: the
  component makes network or IPC calls.* Retries only on safe-to-repeat
  operations.
- **Observability.** *When: the component is deployed or long-running.*
  Structured logs, correlated across components.
- **Performance budgets.** *When: budgets were set in the interview.*
- **Accessibility.** *When: a component has a UI.*
- **Safe migrations.** *When: persisted data.* Every schema change is a
  migration, reversible where possible.

**Security & dependencies**
- ★ **No secrets in the repo.** Secrets come from the environment or a secret
  store.
- ★ **Every new dependency has a recorded reason** and is pinned.

**History**
- ★ **Clean, readable history.** Each commit is one logical change, holds
  only the files changed for it, passes checks on its own, and has a message
  that explains why.

**Agent conduct**
- ★ **Evidence before "done."** No claim of success without running the check
  that shows it.
- ★ **Never weaken a check to pass it.** No skipped tests, loosened lint, or
  catch-all exception handlers, and no mocking the thing under test. A type
  error from an outdated dependency is fixed by upgrading it, not by removing
  or downgrading code. If a check is wrong in one place, record why in a
  decision that names the path and the rule, then make the exception there.
- ★ **Stay in scope.** No drive-by refactors of code the task doesn't touch.
- ★ **Subtract before you add.** In the code a task touches, first remove
  what's dead there: unused code, redundant checks, stubs. A new internal API
  replaces the old one in the same change: every caller migrated, the old one
  deleted, no compatibility layer.
- ★ **Smallest complete change** (from ponytail, MIT, as the next three).
  Take the first option that fully works: skip what nobody asked for, reuse
  the codebase, then the standard library or platform, then an installed
  dependency, then one line, and only then new code. No dependency for a few
  lines, no unrequested abstraction, option or config.
  Never cut validation at trust boundaries, error handling that prevents
  data loss, security, accessibility, or anything asked for. These four apply
  at ponytail's "full" level, always (no lite or ultra), and session start
  and subagent start put them in context, so they steer code as it's
  written, not only at review.
- ★ **Scope before writing.** List every place a change must reach (callers,
  tests, fixtures, config, exports) and what it could break for users, then
  finish all of it.
- ★ **Fix bugs at the root.** Find every caller and fix the cause once, in the
  shared code. Moved or merged code keeps its validation and error handling.
- ★ **Lean structure.** Merge near-copies that must change together; split by
  job, never by line count; between equal-size options, the one correct on
  edge cases.
- ★ **Never block on the human.** Don't stop to ask about reversible work.
  When a requirement is ambiguous, make the reasonable choice, record it in
  the decision log, and say what you chose. Ask first only when the choice
  sets product direction or can't be undone: rewriting the main branch,
  deploys, deleting data, messages to people.
- ★ **Definition of done:** tests written and passing, types and lint clean,
  docs updated, committed per the history principle, reviewer passed (§9).

## 7. What the skeleton contains

Every file below is written by the area skill that owns it. Exact layout is
the builder's, with these constraints:

- **The principles file**: one file, the single source of truth. It must be
  both human-readable (statement, rationale) and machine-readable by hooks
  (when-it-applies flags, thresholds, risk path patterns, per-component
  overrides, doc-mapping). The format is the builder's (e.g. YAML, or Markdown
  with structured front matter).
- **CLAUDE.md**: short. The principles in brief, working rules for the
  agent (read before editing, commit only its own files, re-read before
  reporting), how it talks to the user (answer first, say whether it agrees,
  concise), per-component commands
  (setup/test/run/lint/typecheck), the definition of done, the commit
  convention, and pointers to the principles file and docs. It does not
  duplicate the principles file's parameters.
- **docs/**: product brief (identity and acceptance checks), architecture
  (components, stacks, contracts, reasons), decisions (ADR-style decision
  log, seeded by the interview), contributing guide (incl. commit convention),
  glossary (when applicable), design language (when defined), UI/visual
  system (when applicable), build/CI/hosting, security, dependency log,
  observability, release process, data/migrations (when applicable),
  performance budgets (when applicable).
- **LICENSE**, **README** (identity plus how to set up/test/run).
- **`.claude/settings.json`**: permissions matched to each component's stack
  (allow its test/build/lint commands, deny dangerous ones), hooks wired to
  the kit's scripts.
- **Git hooks**: `commit-msg` check, plus whatever the mechanical checks need.
- **Repository checks** (§8a): a root `mise.toml` pinning the check tools,
  their tool configs, a `scheduled.yml` workflow, and the check scripts under
  `.claude/alpha/checks/`.
- **Per component:** the stack's config files (package manifest, lockfile,
  tool configs with strict settings) and an empty test layout with the
  runner wired up so `test` runs green from day one. No app code. Any minimal
  test that proves the wiring must test the setup itself, not app behavior.
  The approach is the builder's.
- **CI config** running the same one-command checks per component (my call:
  the user listed build pipeline as a principle; CI is how it's enforced).
- **Self-contained enforcement** (my call, following §11's rule that kit
  changes never reach existing projects): the hook scripts, the
  `principles-reviewer` agent, and the `commit` skill and `committer` agent
  are **copied into the project** (e.g. under `.claude/`), not referenced
  from the installed plugin. A fresh clone works on any machine, in CI, and
  for collaborators, with no plugin installed.
- **Nothing kit-specific at the root, no placeholder sources (user
  decision).** Everything alpha owns (hooks, git hooks, interview answers,
  manifest, local state) lives under `.claude/alpha/`. Components get only
  their manifests, lockfiles, tool configs, and a setup test, with no `src/`
  files until real code is written. In a monorepo, the components of a stack
  whose recipe has a `[workspace]` share it at the repository root (Rust: one
  Cargo workspace with one `Cargo.lock`, toolchain, `clippy.toml` and
  `target/`; decision 0027); the components answer `"workspace": false`
  keeps each a package of its own.
- **Kit metadata**: which kit version generated the project, and the
  interview state, so the project can be compared with later kit defaults
  on request.
- The kit runs `git init` and commits the skeleton in a few meaningful,
  convention-following commits, not one blob.

## 8. Mechanical checks (always on, cheap)

Run as Claude Code hooks and git hooks. Each failure message follows the
fail-helpfully principle: what's wrong, and how to fix it.

- After edits: format, lint, type-check on touched files (per component's
  stack).
- Before "done" (Stop): the type check and structure check of the affected
  components pass.
- The full test suite of each changed component passes at one checkpoint,
  `testing.run` (user decision, 2026-11-13, decision 0024). `at-merge`, the
  default: before Claude's work reaches main (a push to main, or a pull
  request merge). Claude runs `python3 .claude/alpha/hooks/stop_checks.py
  tests`, which remembers a pass while the component's files stay the same,
  and the command guard blocks the push or merge without one. `at-stop`: at
  every Stop, as before; for suites that take seconds. A project whose
  principles file has no `testing.run` keeps `at-stop` until `alpha update`
  upgrades it.
- Code changed with no test changes → flag.
- Public behavior changed (per the doc-mapping in the principles file) with
  no doc changes → flag.
- New or changed dependency without a dependency-log entry → flag.
- Secrets in the diff → block.
- Hand edits to lockfiles and other protected paths → block.
- `commit-msg`: type, scope format, subject length, imperative mood →
  reject. The project's scopes are suggestions; any well-formed scope passes,
  so an area outside the list (pstack's habit) works too.
- `--no-verify` (or an abbreviation of it), `core.hooksPath` overridden
  through `-c`, `--config-env` or `GIT_CONFIG_*`, a plain `--force` push, a
  `--force-with-lease` push to the main branch, and `--amend` of a commit
  already on the remote main → block
  (for Claude, via Claude Code hooks; see §9). Claude may rebase its own
  branch and push it with `--force-with-lease`.
- Git commands that stage, stash or discard changes nobody named (`git add
  -A`/`.`, `commit -a`, `reset --hard` while tracked files have uncommitted
  changes, `checkout .`/`restore .`, `stash`) → block (for Claude); `git clean` stays allowed, except `-x`/`-X`. The tree may hold the
  user's or another session's uncommitted work; Claude names its files.
- Disabling or skipping tests, or loosening lint/type settings → block,
  until an accepted decision record names the file and says why.

Per-edit hooks must be fast enough not to slow down normal work. Exact
budgets are the builder's call.

## 8a. Repository checks and the tool registry

Beyond the checks in §8, a generated project gets repository checks: tools
that look at the whole repo, not one component. They run at Stop (the fast
ones) and in CI, which is the gate.

Decisions:

- **D1 Toolchain file.** Repo-check tools are pinned in a generated root
  `mise.toml`. CI installs them with `jdx/mise-action`; bootstrap runs
  `mise trust`, `mise install <the project's tools>` and `mise run
  --continue-on-error ci`. Generated projects now need mise, the same way
  they need uv or pnpm.
- **D1a Every failure at once.** `mise run` cancels the other tasks after the
  first failure, so CI and bootstrap run `ci` and `scheduled` with
  `--continue-on-error`.
- **D1b No global tools.** The generated `mise.toml` sets
  `[settings.task] run_auto_install = false`, so a task (at Stop, or `mise
  run ci`) doesn't install missing tools from the user's global mise config.
- **D2 No hk or pre-commit/pre-push hooks.** §9 keeps `commit-msg` as the only
  git hook that binds everyone. Claude gets the fast repo checks at Stop, and
  CI is the gate.
- **D3 Facts, not questions.** Gates switch on from facts already in the
  answers. There are two new tunables, each offered inside an existing round
  with a recommended default: `dependencies.cooldown_days` (7) and
  `testing.diff_coverage` (80). No new area. This keeps interview cost flat.
  `testing.exhaustive` (off, 2026-11-13) joins the testing round the same
  way, and `testing.mutants` (on, 2026-11-14) only decides whether an
  exhaustive project also gets the mutants gate.
- **D4 Existing projects gain them through `alpha update`** (decision 0022,
  2026-11-13; it replaces "existing projects stay as they are"). When an
  older kit set the project up, `alpha update` upgrades it to the current
  kit, gates included; see §5a.
- **D5 Python import rules aren't generated.** import-linter needs packages a
  skeleton doesn't have. The Python recipe gains a reviewer-checked rule to
  add contracts once packages exist. TypeScript gets dependency-cruiser with
  rules that need no app code (no cycles, no production import of a dev
  dependency).
- **D6 Kept as alpha's picks:** pyright, Biome, Dependabot, and alpha's
  regex secret check at Stop, for new projects. An adopted repo keeps the
  tools that meet the principle (§5b, A1), and its legacy findings are
  baselined (§8b).
- **D7 Links.** lychee runs `--offline` on pull requests and at Stop; the
  online check runs on the schedule only, so PRs don't flake.
- **D8 Toolchain freshness.** The scheduled workflow fails when `mise outdated`
  lists a pinned repo-check tool. Dependabot doesn't update `mise.toml`, and
  a failing scheduled run emails the owner. It fails almost weekly, so it is
  its own step after the scans (not part of the `scheduled` task), and its
  failure says to run `mise upgrade --bump --no-global` and commit
  `mise.toml`.
- **D9 Secrets in the working tree.** betterleaks `dir` also reads gitignored
  files, where local secrets belong (`.env`). So the check runs it through
  `.claude/alpha/checks/secret_scan.py`, which passes only the files git
  lists (`git ls-files --cached --others --exclude-standard`): a folder
  ignored by its own `.gitignore` is skipped, and `.env.example` is still
  scanned. A generated `.betterleaks.toml` extends the default rules with a
  path allowlist of the lockfiles.
- **D10 squawk only for SQL migrations.** squawk lints added `.sql` files, so
  it applies only to a PostgreSQL store whose migration tool writes SQL
  (`SQL_MIGRATION_TOOLS` in `principles.py`); Alembic gets none.

The checks. "Stop" means the check also runs in the Stop hook. "When" is
where CI runs it: `pr`, `schedule`, or `both`.

| id | tool | command | globs | stop | when | applies when |
|---|---|---|---|---|---|---|
| actions | jactionlint | lint `.github/` | `.github/**` | yes | pr | `build.ci == "github-actions"` |
| secrets | betterleaks | `secret_scan.py`: scan the files git doesn't ignore, `--config .betterleaks.toml` | `**` | no | pr | always |
| vulns | osv-scanner | `scan source --no-ignore` on each lockfile's folder, not below it (decision 0026) | lockfiles | no | both | any component has lockfiles |
| typos | typos | `typos` | `**` | yes | pr | always |
| markdown | rumdl | `rumdl check .` | `**/*.md` | yes | pr | always |
| links | lychee | `lychee --offline --no-progress .` | `**/*.md` | yes | pr | always |
| links-online | lychee | `lychee --no-progress .` | none | no | schedule | always |
| agent-config | agnix | strict lint of `.` | `CLAUDE.md`, `.claude/**` | yes | pr | always |
| migrations | none | `python3 .claude/alpha/checks/diff_checks.py immutable-migrations` | none | no | pr | `data.migration_paths` non-empty |
| squawk | squawk | `python3 .claude/alpha/checks/diff_checks.py squawk` | none | no | pr | `data.squawk_paths` non-empty (PostgreSQL with SQL migrations) |
| palette | none | `python3 .claude/alpha/checks/palette.py` | the `palette_files` of `[visuals]` | yes | pr | `design_language.palette_check == "enforce"` |
| baselines | none | `python3 .claude/alpha/checks/diff_checks.py baselines` | none | no | pr | `adoption.baselines` non-empty (§8b) |
| review-dates | none | `python3 .claude/alpha/checks/review_dates.py` | none | no | both | always |
| toolchain | none | `mise outdated --no-global --bump --json \| python3 -c "…"`: prints the outdated tools and, if any, the `mise upgrade --bump --no-global` fix, then exits 1 | none | no | schedule (own step) | always |

Recipe commands. A stack recipe may add these commands to the ones in §3:

- `structure`: checks the component's dependency structure. Python:
  `uv run deptry .`. TypeScript: `pnpm knip && pnpm depcruise --config
  .dependency-cruiser.cjs .`. Rust: `cargo machete`. Bootstrap adds the
  tools, each with a `[why]` line.
- `coverage` and `coverage_report`: run the tests with coverage and name the
  report file, for the diff-coverage gate (`testing.diff_coverage`, 0 turns
  it off). Python: `uv run pytest --cov --cov-branch
  --cov-report=xml:coverage.xml`, report
  `coverage.xml`. TypeScript: `pnpm vitest run --coverage
  --coverage.reporter=cobertura`, report `coverage/cobertura-coverage.xml`.
  Rust: `cargo +nightly-YYYY-MM-DD llvm-cov --branch --cobertura
  --output-path coverage.xml`, report `coverage.xml`; stable Rust records no
  branches, so only this command runs on a dated nightly, which the recipe
  names once under `[vars]` (decision 0028). With exhaustive testing (§6) the
  gate is `--fail-under=100 --branch-coverage`: a changed branch with one
  side untested fails too.
- `mutants`: the mutation-testing gate of an exhaustive project (decision
  0029), run in the component folder on the pull request's diff in
  `pr.diff`. Rust: `cargo mutants --in-diff pr.diff --in-place
  --timeout-multiplier 3`; a surviving mutant fails, one whose tests time
  out counts as caught. CI runs it as the `mutants` step of the component's
  pull-request job; `ALPHA_BASE=<base> mise run ci` runs it locally. The
  diff is `git diff --relative`, so it names files from the component's
  folder, except for a workspace member, whose tree starts at the root.

A recipe's `[vars]` table names values several of its commands share; each
`${name}` in the recipe is filled from it.

The registry (`registry/` in the kit) has one entry per repo-check tool. An
entry holds the tool's pinned version and `pin.command`, the command that
runs it. The generated `mise.toml`, CI and the Stop hook all read the same
entries, so a command is written once.

## 8b. Baselines and the ratchet

For an adopted project (§5b, A2). A generated project has no baselines, and
its files don't change.

- **What a baseline holds.** One file per check under
  `.claude/alpha/baselines/<check-id>.json`. It counts findings per file and
  rule, not per line, so moving code doesn't break it, and it works the same
  for every tool.
- **How a finding is read.** Each check that can be baselined names, as
  data, a command with machine-readable output and a pattern: a regular
  expression with named groups `file` and `rule`. The kit's recipes and the
  registry carry these for their tools; an adopted recipe carries them for
  the repo's tools, and proving the recipe proves that the pattern reads
  the output. The Rust recipe has no readers yet (Clippy and cargo print
  one JSON object per line), so `answers check` refuses a baseline for a
  kit Rust component; an adopted recipe that extends Rust can carry its own.
- **The ratchet.** `ratchet.py <check-id> -- <command>` (copied under
  `.claude/alpha/checks/`) runs the check:
  - a file and rule counted above the baseline fails, and the message names
    each new finding;
  - a failing tool whose output doesn't parse fails, saying the output
    can't be read (fail closed);
  - counts below the baseline tighten it in place, locally (Stop, the edit
    hooks, bootstrap); CI runs it frozen, where a baseline that could
    shrink fails with the command to tighten and commit it.
- **Only baselined checks are wrapped.** The principles file, `mise.toml`
  and CI run a check through the ratchet only while the interview state
  lists a baseline for it. When a burn-down step clears one, `alpha update`
  renders the plain command again.
- **Only shrinking.** Baselines are protected paths, so Claude can't edit
  them, and risk paths, so the reviewer sees every change to them. A
  baseline grows only through `alpha baseline capture --check <id>
  --decision <NNNN>`, with an accepted decision record naming the check and
  why, as loosening a principle needs (§6). The gate is the pull request: the
  `baselines` check compares each baseline with where the branch left the
  base, and fails when a count rises, unless an accepted decision record
  names the check (in backticks) for the first time on the branch. Capture
  holds to the same rule. A check newly listed in the change starts its
  baseline there, as the adoption's own pull request does. A command guard
  can't tell a capture from a hand-written file; the diff can.
- **The edit hooks.** The post-edit lint runs over the whole edited file, so
  for a baselined check it goes through the ratchet too: legacy findings
  already in the file don't block an edit, new ones do.
- **Not ratcheted:**
  - the format check, which plan step P1 fixes once;
  - secrets, where a real one is a P0 step and a false positive goes into
    `.betterleaksignore`;
  - known vulnerabilities, which use `osv-scanner.toml` exceptions with a
    reason and a review date (the `review-dates` check).

`alpha baseline show` prints the counts per check, component and rule, and
`docs/adoption.md` shows the same numbers.

## 9. The principles reviewer

A Claude Code agent that reviews batched changes against the project's
principles file and decision log, reporting each problem against the
specific principle it breaks. Findings block "done" until fixed or accepted,
and every acceptance is recorded in the decision log. Claude may accept a
finding it disproves; the next review reads that disproof and reports it
again if it doesn't hold. A finding on a risk path is accepted only by the
user.

**Beyond the project's rules** (from ponytail's review, MIT). The reviewer
also looks, in order of importance, for bugs, security holes and data loss,
what breaks at the project's expected load (`performance.expected_load`,
asked in the interview and printed in the brief), risky logic without a test,
real slowness, and code that shouldn't exist. A finding names the principle it
breaks, or else its lens (`lens:bug`, `lens:risk`, `lens:scale`,
`lens:speed`, `lens:lean`). Every finding needs a concrete case (this input
leads to this wrong result), and proposes the smallest fix, preferring one
that deletes code. A `shortcut: <the limit>, <when to upgrade>` comment is a
decision, not a finding, until the expected load crosses its limit.

**Tests.** The Stop hook flags source changed without a test change. For a
trivial change (a rename, a constant, wiring), Claude records why with
`review.py untested "<why>" <path>`; the note holds while the file's content
stays the same, and the reviewer checks each one.

**On-demand reports.** Generated projects also get `/review-change` (a
change), `/audit` (the whole repo) and `/debt` (the `shortcut:` ledger), each
adapted from ponytail and changing no code. They don't gate anything.

**When it runs: "review debt".** The project records the last reviewed
commit. Everything after it (plus uncommitted work) is unreviewed. When an
agent signals done, a cheap script decides whether the reviewer runs:

1. **Size:** unreviewed changes exceed a threshold. Default: ~200 changed
   lines or 5+ files, excluding tests and docs.
2. **Risk, regardless of size:** the change touches a contract, a migration,
   auth/security/secrets-related code, dependencies, build/CI/hosting config,
   adds a component, or edits the principles file.
3. **Checkpoints:** before a push to main or a pull request merge, and at
   the end of a planned piece of work, everything unreviewed is reviewed.
   **Nothing Claude does reaches main unreviewed.** A feature branch can be
   pushed and its pull request opened before the review, so CI runs
   alongside it.

**Worktrees.** The hooks act on the checkout the work happens in: the
edited file's, or the working directory's (following `cd` and `git -C`), not
only the folder the session started in. So each git worktree has its own
checks and review state. Review starts where the branch leaves main, not at
its pushed commit, since a feature branch can be pushed before review; a
rebase onto main, or a merge of main, carries the review along. `gh pr merge`
is checked in the worktree that has the pull request's branch.

**Who it binds (user decision):** review-before-main and the git guardrails
(no `--no-verify`, no plain force-push, no rewriting main, nothing that
sweeps up or discards unnamed changes) are enforced
on **Claude only**, through Claude Code hooks. The user can push by hand
freely. The only git hook that binds everyone is `commit-msg` (format
check). No headless reviewer runs from git hooks.

**User control (user decision).** Every reviewer parameter (size
thresholds, excluded paths, risk path patterns, checkpoints) lives in the
principles file and can be overridden by the user: in the interview, by
calling the agent-workflow area skill later, or by editing the file
directly. There is also a **review mode** setting:

- `at-merge` (default, 2026-11-11, for pstack, which verifies a finished
  change once): only the checkpoint before main. Stop never asks for a
  review, but open findings still block it.
- `batched`: the three triggers above.
- `every-task`: the reviewer runs every time an agent signals done, whatever
  the size.

Changing the mode or a threshold is recorded in the decision log and goes
through the kit-default question (§11), so `every-task` can become the
default for all future projects.

## 10. Git history and the commit tools

The kit ships its own copies of the user's `commit` skill and `committer`
agent (from `~/.claude/commands/commit.md` and `~/.claude/agents/committer.md`)
so every project has them on any machine. Changes when porting:

- **Remove the hard-coded co-author footer.** Use the attribution lines
  Claude Code provides.
- **Don't wait for the user** (pstack): split changes into commits and
  report the split instead of proposing it; amend or rebase the branch's own
  commits before a pull request, but never rewrite main.
- Keep everything else: check the project convention first; atomic splitting
  (`.claude/` changes always separate, formatting separate from behavior);
  conventional types; 50-char imperative subject, which may start lowercase;
  body explains what and why.

The interview writes the project's commit convention (default: conventional
commits, suggested scopes = component names) into CONTRIBUTING and
CLAUDE.md, where the commit skill already looks.

## 11. Kit defaults and how they evolve

- The kit's defaults (principles, conditions, thresholds, preferred stack
  answers) live in a defaults file in this repo. The kit is for this user
  only.
- **Installed from GitHub (user decision, 2026-11-10; replaces reading the
  defaults live from a local checkout).** The kit reads its defaults,
  recipes and tool registry from the plugin as installed. Only an explicit
  `ALPHA_SOURCE` points it at a checkout, for developing the kit and for its
  evals.
- **The user's own layer.** `~/.config/alpha/` (or `ALPHA_CONFIG_DIR`) holds
  the user's defaults (`overrides.toml`, with a `CHANGELOG.md` that records
  the project each change came from and why) and recipes drafted in
  interviews (`recipes/`). It applies on top of the kit's and survives
  plugin updates; the kit's recipe wins for a stack both have.
- When the user overrides a default in a project, the kit asks: "Make this
  the default for future projects too?" Yes → save it in the user's layer,
  so the next project starts from it. No → the override stays in the
  project's decision log only. Changing the kit's own defaults is ordinary
  work on this repo, released by pushing it and updating the plugin.
- Existing projects change with the kit only through `alpha update`, which
  upgrades a project an older kit set up (decision 0022, §5a). The manifest
  records the kit version and defaults used.

## 12. The kit's own quality

The kit follows its own principles:
- Hook scripts have automated tests.
- The skills have evals: scripted interview scenarios ("Python ML
  pipeline, single component", "TypeScript web app + Python API", "Rust
  CLI"). Since Rust got a kit recipe, the fallback path for a stack with no
  recipe is covered by the recipe tests and a live run, not by a scenario.
  They check the generated skeleton: required files
  exist, settings are valid, hooks fire on seeded violations, each component's
  test command runs green, commits follow the convention, and the reviewer
  catches seeded principle violations.
- Seeded violations prove every repo check can fail.
- The kit repo uses its own commit convention and clean history.

## 13. Constraints

- Must run as a Claude Code plugin (skills, agents, hooks). The hook
  mechanisms available are Claude Code's hook events plus git hooks.
- Target machine: macOS (the user's). Hook scripts should need nothing beyond
  what's normally present plus each component's own stack tools.
- Must work with no app code present.

## 14. Left to the builder

- Plugin layout, file formats (including the principles file format), and the
  language for hook scripts.
- Exact question wording, round grouping within each area, and what goes in
  each template.
- Specific tool choices inside the Python, TypeScript and Rust recipes,
  within the defaults named above.
- How "public behavior changed" and "secrets in the diff" are detected.
- How the Stop hook triggers the reviewer (e.g. block with instructions to
  dispatch the agent, or an agent-type hook).
- Interview state format and where it lives in the target folder.
- Order of building: a reasonable cut is `grilling` + identity + components &
  stack + Python/TS recipes + principles file + CLAUDE.md + mechanical hooks
  first, then the remaining areas, then the reviewer and review debt.

## 15. Later (not v1)

