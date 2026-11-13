# Contributing

## One-time setup

```sh
git config core.hooksPath .claude/alpha/githooks
```

Then set up each component:

- `alpha`: `cd . && uv sync`

## Checks

```sh
mise install
mise run check
```

`mise install` installs the pinned tools; `mise run check` runs every component's checks and the repository checks below, the same as CI.

The principles in `docs/principles.toml` name them in `checked_by` as `ci:<name>`: a name in the table is that check, and `ci:tree` is when every CI job ends by checking that the checks left the tree unchanged.

| Check | What it checks | Runs |
|---|---|---|
| secrets | Secrets in the working tree (betterleaks) | pull request |
| vulns | Known vulnerabilities in locked dependencies (osv-scanner) | pull request, weekly |
| typos | Spelling in code and docs (typos) | pull request, at Stop |
| markdown | Markdown style (rumdl) | pull request, at Stop |
| links | Relative links in docs resolve (lychee) | pull request, at Stop |
| links-online | Links to other sites still work (lychee) | weekly |
| agent-config | CLAUDE.md and .claude/ configuration (agnix) | pull request, at Stop |
| shortcuts | Every `shortcut:` comment names when to upgrade | pull request, at Stop |
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

A test that covers an acceptance check names its requirement id (e.g. `R1`) in its name, so each check in docs/product.md traces to a test.

## Documentation

Internal docs (design, decisions, how we work) live in `docs/`. User-facing documentation lives in README.md.

| When these change | Update |
|---|---|
| `src/alpha/cli.py`, `bin/**` | `README.md`, `CLAUDE.md` |
| `skills/new-project/**`, `skills/adopt/**`, `skills/extend/**` | `README.md` |

The Stop hook blocks a change to these paths that leaves the docs untouched.

## Branching

Feature branches: short-lived branches merged into main through pull requests, each leaving the checks green. Before opening a pull request, rebase the branch on main into small, ordered commits and push it with --force-with-lease; the hooks block a plain --force and any rewrite of main.

Claude runs the principles reviewer before its work reaches main: a push to main, or merging a pull request. People can push by hand.
