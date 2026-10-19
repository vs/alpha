# alpha

alpha is a Claude Code plugin that interviews you about a new project and generates a skeleton: config, docs, test wiring and enforcement, with no app code. Design: [docs/superpowers/specs/2026-10-19-project-kit-design.md](docs/superpowers/specs/2026-10-19-project-kit-design.md).

## Dev commands

- `uv run pytest`
- `uv run ruff check` and `uv run ruff format`
- `uv run pyright`

## Rules

- The kit follows its own principles (spec §12).
- Commits use conventional commits with scopes = component names. The description after `type(scope): ` is at most 50 chars, imperative, capitalized, no trailing period. Body lines wrap at 72.
