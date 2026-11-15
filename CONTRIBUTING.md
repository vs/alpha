# Contributing

## One-time setup

```sh
git config core.hooksPath .claude/alpha/githooks
```

Then set up each component:

- `alpha`: `cd . && uv sync`

## Components

Layout: single.

| Name | Path | Kind | Stack | Traits |
|---|---|---|---|---|
| alpha | . | cli | alpha-python | network_calls, persisted_data, nontrivial_logic |

Components do not communicate with each other.

### Tool choices

- alpha-python: the stack's own toolchain. Commands: `uv sync`, `uv run pytest`, `uv run ruff check src tests project-files`, `uv run ruff format src tests project-files`, `uv run ruff format --check src tests project-files`, `uv run pyright`, `uv run deptry . --extend-exclude .claude` (less proven: recipe drafted for this project)

## Checks

```sh
mise install
mise run check
```

`mise install` installs the pinned tools; `mise run check` runs every component's checks and the repository checks below, the same as CI.

The principles in `docs/principles.toml` name them in `checked_by` as `ci:<name>`: a name in the table is that check, and `ci:tree` is when every CI job ends by checking that the checks left the tree unchanged; `ci:diff-coverage` is when a pull request's job fails when its tests cover less of the changed lines than `testing.diff_coverage`.

| Check | What it checks | Runs |
|---|---|---|
| secrets | Secrets in the working tree (betterleaks) | pull request |
| vulns | Known vulnerabilities in locked dependencies (osv-scanner) | pull request, weekly |
| typos | Spelling in code and docs (typos) | pull request, at Stop |
| markdown | Markdown style (rumdl) | pull request, at Stop |
| links | Relative links in docs resolve (lychee) | pull request, at Stop |
| links-online | Links to other sites still work (lychee) | weekly |
| agent-config | CLAUDE.md and .claude/ configuration (agnix) | pull request, at Stop |
| review-dates | Suppressions past their review date | pull request, weekly |
| toolchain | Pinned tools that have a newer release | weekly |

## Commit convention

Conventional commits: `type(scope): description`.

- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `build`, `chore`, `perf`, `ci`, `revert`
- Scopes: `alpha`, `hooks`, `recipes`, `defaults`, `spec`, or another area the commit touches
- The description is at most 50 characters, imperative, with no trailing period; it may start lowercase, e.g. with the symbol it changes.
- Body lines wrap at 72 characters.

## Testing

| Component | Levels |
|---|---|
| alpha | unit, integration, end-to-end |

Put each level's tests under `tests/<level>/` in the component.

A test that covers an acceptance check names its requirement id (e.g. `R1`) in its name, so each check in docs/specification.md traces to a test.

## Documentation

Internal docs (the specification, the principles) live in `docs/`. User-facing documentation lives in README.md.

| When these change | Update |
|---|---|
| `src/alpha/cli.py`, `bin/**` | `README.md`, `CLAUDE.md` |
| `skills/install/**`, `skills/extend/**`, `skills/specify/**`, `skills/update/**`, `skills/uninstall/**`, `skills/purge/**`, `skills/do/**` | `README.md` |

The Stop hook blocks a change to these paths that leaves the docs untouched.

## Branching

Feature branches: short-lived branches merged into main through pull requests, each leaving the checks green. Before opening a pull request, rebase the branch on main into small, ordered commits and push it with --force-with-lease; the hooks block a plain --force and any rewrite of main.

Claude runs the principles reviewer and each changed component's full test suite before its work reaches main: a push to main, or merging a pull request. People can push by hand.

## Build, CI and hosting

### CI

No CI: see build-hosting-upfront under Overrides below.

### Artifacts and hosting

| Component | Artifact | Hosting |
|---|---|---|
| alpha | package | - |

### Environments

None: nothing is deployed.

Hosting is decided and documented here; alpha creates no cloud resources and no deploy jobs.

## Releases

Semantic versioning (MAJOR.MINOR.PATCH): a breaking change bumps MAJOR, a new feature MINOR, a fix PATCH.

One version for the whole repository.

Changes are written up in the GitHub release notes for each version.

### Cutting a release

Bump the version in .claude-plugin/plugin.json, pyproject.toml and src/alpha/__init__.py (plus uv.lock) in a chore: Release X.Y.Z commit on main, tag vX.Y.Z and publish a GitHub release with its notes. Users get it with claude plugin marketplace update alpha.

## Security

### Secrets

Nothing is deployed.

Locally, secrets live in `.env` files, which git ignores; never commit them. Claude can't edit them, and the Stop hook blocks a change that adds a secret to the repository.

### Protected paths

Claude can't edit these. Lockfiles change only through the package manager; change the others by hand.

- `**/.env`
- `**/.env.*`
- `**/*.pem`
- `**/*.key`
- `uv.lock`

## Overrides

| Principle | Change | Scope | Reason |
|---|---|---|---|
| build-hosting-upfront | loosen | project | mise run check runs locally before each commit, and the slow tests need real toolchains that CI should not spend. |

## Exceptions

A check skipped or loosened in one place, or a baseline loosened, needs a row here naming the path and the check, with the reason; the checks look for it.

| Path | Check | Reason |
|---|---|---|
| `project-files/hooks/_common.py` | `PLC0415` | The `tomllib` import in `load_principles` is late: hooks must parse on Python 3.9, which has no `tomllib`. It moves to the top once the hooks require Python 3.11. |
| `project-files/hooks/session_start.py` | `PLC0415` | The `tomllib` imports in `principles_problem` and `_lenient_principles`, for the same reason. |
| `project-files/hooks/stop_checks.py` | `PLC0415` | The `tomllib` import after `check_python()`, for the same reason. |
