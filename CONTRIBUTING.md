# Contributing

## Working with alpha

- `/alpha:install` adopted this repo on `alpha/adopt`; run again, it carries out the next step of `docs/alpha/adoption.md` while one is left.
- `/alpha:update [request]` keeps it current: with no request it brings alpha's files to the installed kit; with one it adds or changes a component or a setup answer, or settles a product area (`/alpha:update performance`).
- `/alpha:do <task>` works each task by a playbook; a feature goes through research, a spec and a plan the user approves before any code.
- `/alpha:uninstall` switches alpha's hooks off and `/alpha:install` switches them back on; `/alpha:purge` removes alpha in one commit.

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
| alpha | . | cli | alpha-python | network_calls, nontrivial_logic |

Components do not communicate with each other.

### Tool choices

- alpha-python: the stack's own toolchain. Commands: `uv sync`, `uv run pytest`, `uv run ruff check --extend-exclude .claude`, `uv run ruff format --extend-exclude .claude`, `uv run ruff format --check --extend-exclude .claude`, `uv run pyright`, `uv run deptry . --extend-exclude .claude` (less proven: recipe drafted for this project)

## Checks

```sh
mise install
mise run check
```

`mise install` installs the pinned tools; `mise run check` runs every component's checks and the repository checks below, the same as CI.

The principles in `docs/alpha/principles.toml` name them in `checked_by` as `ci:<name>`: a name in the table is that check, and `ci:tree` is when every CI job ends by checking that the checks left the tree unchanged; `ci:diff-coverage` is when a pull request's job fails when its tests cover less of the changed lines than `testing.diff_coverage`.

| Check | What it checks | Runs |
|---|---|---|
| actions | GitHub Actions workflows (jactionlint) | pull request, at Stop |
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

The default run (`uv run pytest`) also checks the CLI on Python 3.11, alpha's minimum, and the version guard on 3.9: uv downloads those interpreters the first time, so that run needs the network once. No test skips when a tool is missing: the slow tests need uv, pnpm, mise and cargo, and fail without them.

A test that covers an acceptance check names its requirement id (e.g. `R1`) in its name, so each check in docs/alpha/specification.md traces to a test.

## Documentation

alpha's docs (the specification, the principles, the dependency log) live in `docs/alpha/`. User-facing documentation lives in README.md.

| When these change | Update |
|---|---|
| `src/alpha/cli.py`, `bin/alpha`, `skills/*/SKILL.md` | `docs/specification.md` |

The Stop hook blocks a change to these paths that leaves the docs untouched.

## Branching

Feature branches: short-lived branches merged into main through pull requests, each leaving the checks green. Before opening a pull request, rebase the branch on main into small, ordered commits and push it with --force-with-lease; the hooks block a plain --force and any rewrite of main.

Claude runs the principles reviewer and each changed component's full test suite before its work reaches main: a push to main, or merging a pull request. People can push by hand.

## Build, CI and hosting

### CI

GitHub Actions runs `.github/workflows/ci.yml` on every push to main and every pull request: one job per component, running its checks in order.

| Component | Checks |
|---|---|
| alpha | `uv sync`, `uv run ruff format --check --extend-exclude .claude`, `uv run ruff check --extend-exclude .claude`, `uv run pyright`, `uv run deptry . --extend-exclude .claude`, `uv run pytest` |

A `slow` job also runs `uv run pytest -m slow`: the end-to-end tests the default run leaves out, which bootstrap real projects with uv, pnpm, mise and cargo and need the network.

A pull request that changes only files no test reads (`docs/alpha/`, this repo's own `.claude/`, `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`) runs only the `repo` job; a `changes` job decides, and a push to main always runs every job.

### Artifacts and hosting

| Component | Artifact | Hosting |
|---|---|---|
| alpha | other | - |

### Environments

None: nothing is deployed.

Hosting is decided and documented here; alpha creates no cloud resources and no deploy jobs.

## Releases

Semantic versioning (MAJOR.MINOR.PATCH): a breaking change bumps MAJOR, a new feature MINOR, a fix PATCH.

One version for the whole repository.

Changes are written up in the GitHub release notes for each version.

### Cutting a release

Bump the version in pyproject.toml, src/alpha/__init__.py and .claude-plugin/plugin.json (then uv lock), and run bin/alpha update . from this checkout, which is the new kit, so this repo records the new kit_version in the same "chore: Release X.Y.Z" pull request; after it merges, tag vX.Y.Z on main and publish a GitHub release with the notes. Users get it with claude plugin marketplace update alpha, then claude plugin update alpha@alpha.

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

## Exceptions

A check skipped or loosened in one place, or a baseline loosened, needs a row here naming the path and the check, with the reason; the checks look for it.

| Path | Check | Reason |
|---|---|---|
