# Project kit: design

Date: 2026-10-19
Status: draft for approval

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
- First-class recipes for **Python** (ML) and **TypeScript** (web apps). Any
  other stack still works, set up from that stack's usual conventions and
  marked as less proven.

**Non-goals (v1)**
- No app code, not even a hello-world. The skeleton is configuration, docs,
  test wiring, and enforcement only.
- No existing projects. v1 runs only on empty folders. Bringing existing
  code up to the principles is a later, separate set of skills.
  **Exception (user decision):** area skills may be called directly on a
  project *the kit generated* to extend it (see §5a). They never touch app
  code.
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

A Claude Code plugin, developed in this repo (`/Users/vs/workspace/alpha`),
installed once and used everywhere.

| Part | What it is |
|---|---|
| `new-project` skill | User-invoked entry point. Runs the interview across all areas, then generates the skeleton. Resumable. |
| `grilling` skill | Shared interview primitive used by `new-project` and every area skill (design tree, rounds, recommended answers; see §4). |
| Area skills | One per area in §5. Each owns its questions, its principles, and the files it writes. Callable by `new-project` and directly. |
| Stack recipes | Per-stack data and templates: test runner, linter/formatter, type checker, commands, permission lists, and stack rules. Full for Python and TypeScript, generic fallback for others. |
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
  Recommendations come from the kit defaults.
- **Facts are the kit's job, decisions are the user's.** Never ask what can be
  looked up (installed tool versions, whether `gh` is authenticated, the latest
  stable version of a framework).
- **Decisions are recorded as they're made**, as decision records under
  `docs/decisions/` (ADR-style), not reconstructed at the end. My call on
  granularity, to avoid 100+ files: **one record per area** summarizing its
  decisions, plus **a separate record for each override** of a kit default
  and for each decision made later in the project's life.
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
   and how acceptance checks map to tests.
6. **UI/UX** (only if a component has a UI). The set of visual tools that
   make up the UI: design tokens, component library, icon set, typography,
   theming, plus visual regression and accessibility checks.
7. **Documentation.** Internal vs external docs, where external docs live, and
   how they're kept in step with code (which code paths map to which docs, for
   the docs-drift check).
8. **Build, CI, hosting.** How each component is built, the CI provider and
   what it runs, where each component is hosted, environments.
9. **Security & secrets.** Where secrets live, what's never committed,
   auth approach if any, protected paths.
10. **Dependencies.** Policy for adding, pinning, and upgrading. Lockfiles. A
    dependency log entry with the reason for each new dependency.
11. **Observability.** Logging format (structured), levels, correlation across
    components, metrics or tracing if needed.
12. **Versioning & releases.** Versioning scheme, changelog, release process.
13. **Data & migrations** (only if there's persisted data). Storage, schema
    ownership, migration tool and rules. For ML: data versioning, seeds,
    experiment tracking.
14. **Accessibility** (only with a UI). Target level, automated checks.
15. **Performance.** Budgets per component (response time, bundle size,
    memory, training/inference time) and how they're measured.
16. **Git history.** Commit convention and scopes (per component), branching
    model, what's protected (§10).
17. **Agent workflow.** Hooks, permissions, review thresholds and risk
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
- On a folder the kit didn't generate, refuse and explain that existing
  projects are out of scope for v1.

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
- **A deliberate visual system.** *When: a component has a UI.* The UI is
  built from the declared set of visual tools, not ad-hoc styles.
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
  or downgrading code. If a check is wrong, raise it with the user.
- ★ **Stay in scope.** No drive-by refactors of code the task doesn't touch.
- ★ **Subtract before you add.** In the code a task touches, first remove
  what's dead there: unused code, redundant checks, stubs. A new internal API
  replaces the old one in the same change: every caller migrated, the old one
  deleted, no compatibility layer.
- ★ **Ask when ambiguous**, and record the answer in the decision log.
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
  glossary (when applicable), UI/visual system (when applicable), build/CI/
  hosting, security, dependency log, observability, release process, data/
  migrations (when applicable), performance budgets (when applicable).
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
  files until real code is written.
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
- Before "done" (Stop): tests for affected components pass.
- Code changed with no test changes → flag.
- Public behavior changed (per the doc-mapping in the principles file) with
  no doc changes → flag.
- New or changed dependency without a dependency-log entry → flag.
- Secrets in the diff → block.
- Hand edits to lockfiles and other protected paths → block.
- `commit-msg`: type, scope, subject length, imperative mood → reject.
- `--no-verify`, force-push, and `--amend` of pushed commits → block (for
  Claude, via Claude Code hooks; see §9).
- Git commands that stage, stash or discard changes nobody named (`git add
  -A`/`.`, `commit -a`, `reset --hard`, `checkout .`/`restore .`, `stash`)
  → block (for Claude); `git clean` stays allowed, except `-x`/`-X`. The tree may hold the
  user's or another session's uncommitted work; Claude names its files.
- Disabling or skipping tests, or loosening lint/type settings → block (or
  flag for user approval).

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
- **D4 Existing projects stay as they are.** `alpha update` renders before and
  after with the current kit, so kit changes cancel out and old projects
  don't gain these gates. This matches §11. Opting an old project in is out
  of scope. When an older kit generated the project (no `[[repo_checks]]` in
  its principles), the overlaps can be kit changes, so `alpha update` says so,
  and lists the newer kit's files as left out, not as deleted.
- **D5 Python import rules aren't generated.** import-linter needs packages a
  skeleton doesn't have. The Python recipe gains a reviewer-checked rule to
  add contracts once packages exist. TypeScript gets dependency-cruiser with
  rules that need no app code (no cycles, no production import of a dev
  dependency).
- **D6 Kept as alpha's picks:** pyright, Biome, Dependabot, alpha's regex
  secret check at Stop, and new-projects-only scope. Using alpha on existing
  repos is not covered.
- **D7 Links.** lychee runs `--offline` on pull requests and at Stop; the
  online check runs on the schedule only, so PRs don't flake.
- **D8 Toolchain freshness.** The scheduled workflow fails when `mise outdated`
  lists a pinned repo-check tool. Dependabot doesn't update `mise.toml`, and
  a failing scheduled run emails the owner. It fails almost weekly, so it is
  its own step after the scans (not part of the `scheduled` task), and its
  failure says to run `mise upgrade --bump --no-global` and commit
  `mise.toml`.
- **D9 Secrets in the working tree.** betterleaks `dir` also reads gitignored
  files, where local secrets belong (`.env`). A generated `.betterleaks.toml`
  extends the default rules with a path allowlist from the same excludes as
  the other tool configs (`.env.example` is still scanned).
- **D10 squawk only for SQL migrations.** squawk lints added `.sql` files, so
  it applies only to a PostgreSQL store whose migration tool writes SQL
  (`SQL_MIGRATION_TOOLS` in `principles.py`); Alembic gets none.

The checks. "Stop" means the check also runs in the Stop hook. "When" is
where CI runs it: `pr`, `schedule`, or `both`.

| id | tool | command | globs | stop | when | applies when |
|---|---|---|---|---|---|---|
| actions | jactionlint | lint `.github/` | `.github/**` | yes | pr | `build.ci == "github-actions"` |
| secrets | betterleaks | scan the working tree, `--config .betterleaks.toml` | `**` | no | pr | always |
| vulns | osv-scanner | scan source recursively | lockfiles | no | both | any component has lockfiles |
| typos | typos | `typos` | `**` | yes | pr | always |
| markdown | rumdl | `rumdl check .` | `**/*.md` | yes | pr | always |
| links | lychee | `lychee --offline --no-progress .` | `**/*.md` | yes | pr | always |
| links-online | lychee | `lychee --no-progress .` | none | no | schedule | always |
| agent-config | agnix | strict lint of `.` | `CLAUDE.md`, `.claude/**` | yes | pr | always |
| migrations | none | `python3 .claude/alpha/checks/diff_checks.py immutable-migrations` | none | no | pr | `data.migration_paths` non-empty |
| squawk | squawk | `python3 .claude/alpha/checks/diff_checks.py squawk` | none | no | pr | `data.squawk_paths` non-empty (PostgreSQL with SQL migrations) |
| review-dates | none | `python3 .claude/alpha/checks/review_dates.py` | none | no | both | always |
| toolchain | none | `mise outdated --no-global --bump --json \| python3 -c "…"`: prints the outdated tools and, if any, the `mise upgrade --bump --no-global` fix, then exits 1 | none | no | schedule (own step) | always |

Recipe commands. A stack recipe may add two commands to the ones in §3:

- `structure`: checks the component's dependency structure. Python:
  `uv run deptry .`. TypeScript: `pnpm knip && pnpm depcruise --config
  .dependency-cruiser.cjs .`. Bootstrap adds the tools, each with a `[why]`
  line.
- `coverage` and `coverage_report`: run the tests with coverage and name the
  report file, for the diff-coverage gate (`testing.diff_coverage`, 0 turns
  it off). Python: `uv run pytest --cov --cov-report=xml:coverage.xml`, report
  `coverage.xml`. TypeScript: `pnpm vitest run --coverage
  --coverage.reporter=cobertura`, report `coverage/cobertura-coverage.xml`.

The registry (`registry/` in the kit) has one entry per repo-check tool. An
entry holds the tool's pinned version and `pin.command`, the command that
runs it. The generated `mise.toml`, CI and the Stop hook all read the same
entries, so a command is written once.

## 9. The principles reviewer

A Claude Code agent that reviews batched changes against the project's
principles file and decision log, reporting each problem against the
specific principle it breaks. Findings block "done" until fixed or knowingly
accepted by the user. An acceptance is recorded in the decision log.

**When it runs: "review debt".** The project records the last reviewed
commit. Everything after it (plus uncommitted work) is unreviewed. When an
agent signals done, a cheap script decides whether the reviewer runs:

1. **Size:** unreviewed changes exceed a threshold. Default: ~200 changed
   lines or 5+ files, excluding tests and docs.
2. **Risk, regardless of size:** the change touches a contract, a migration,
   auth/security/secrets-related code, dependencies, build/CI/hosting config,
   adds a component, or edits the principles file.
3. **Checkpoints:** before push/PR and at the end of a planned piece of
   work, everything unreviewed is reviewed. **Nothing Claude pushes leaves
   the machine unreviewed.**

**Who it binds (user decision):** review-before-push and the git guardrails
(no `--no-verify`, no force-push, no amending pushed commits, nothing that
sweeps up or discards unnamed changes) are enforced
on **Claude only**, through Claude Code hooks. The user can push by hand
freely. The only git hook that binds everyone is `commit-msg` (format
check). No headless reviewer runs from git hooks.

**User control (user decision).** Every reviewer parameter (size
thresholds, excluded paths, risk path patterns, checkpoints) lives in the
principles file and can be overridden by the user: in the interview, by
calling the agent-workflow area skill later, or by editing the file
directly. There is also a **review mode** setting:

- `batched` (default): the three triggers above.
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
- Keep everything else: check the project convention first; atomic splitting
  (`.claude/` changes always separate, formatting separate from behavior);
  amend only unpushed commits; conventional types; 50-char imperative
  subject; body explains what and why.

The interview writes the project's commit convention (default: conventional
commits, scopes = component names) into CONTRIBUTING and CLAUDE.md, where the
commit skill already looks.

## 11. Kit defaults and how they evolve

- The kit's defaults (principles, conditions, thresholds, preferred stack
  answers) live in a defaults file in this repo, with a change history:
  each change records the project it came from and why. The kit is for this
  user only.
- **Read live from the repo (user decision).** The installed kit reads the
  defaults from the source repo at a configurable path (default:
  `/Users/vs/workspace/alpha`), so a "yes" takes effect for the very next
  project with no reinstall. If the repo isn't there (another machine), the
  kit falls back to the defaults bundled at install time and says so
  clearly. In that case it can't save a new default, so it records the
  wish in the project's decision log for later.
- When the user overrides a default in a project, the kit asks: "Make this
  the default for future projects too?" Yes → update the kit defaults in this
  repo (the source, not an installed copy) and commit. No → the override stays
  in the project's decision log only.
- Existing projects never change when kit defaults change. A project can be
  compared with current kit defaults only on request (that skill can be added
  later; v1 only needs to record the kit version and defaults used).

## 12. The kit's own quality

The kit follows its own principles:
- Hook scripts have automated tests.
- The skills have evals: scripted interview scenarios (e.g. "Python ML
  pipeline, single component", "TypeScript web app + Python API", "Go CLI"
  for the fallback path). They check the generated skeleton: required files
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
- Specific tool choices inside the Python/TypeScript recipes, within the
  defaults named above.
- How "public behavior changed" and "secrets in the diff" are detected.
- How the Stop hook triggers the reviewer (e.g. block with instructions to
  dispatch the agent, or an agent-type hook).
- Interview state format and where it lives in the target folder.
- Order of building: a reasonable cut is `grilling` + identity + components &
  stack + Python/TS recipes + principles file + CLAUDE.md + mechanical hooks
  first, then the remaining areas, then the reviewer and review debt.

## 15. Later (not v1)

- Skills that bring existing codebases up to the principles.
- Re-syncing a project with newer kit defaults.
- Opting an existing project into newer kit gates (see §8a, D4).
- alpha on existing repos (see §8a, D6).
