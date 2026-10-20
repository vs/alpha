# alpha

alpha is a Claude Code plugin that interviews you about a new project and generates a skeleton: config, docs, test wiring and enforcement, with no app code. Design: [docs/superpowers/specs/2026-10-19-project-kit-design.md](docs/superpowers/specs/2026-10-19-project-kit-design.md).

## Dev commands

- `uv run pytest`
- `uv run ruff check` and `uv run ruff format`
- `uv run pyright`

## Rules

- The kit follows its own principles (spec §12).
- Commits use conventional commits with scopes = component names. The description after `type(scope): ` is at most 50 chars, imperative, capitalized, no trailing period. Body lines wrap at 72.

## Install and verify

Try alpha without installing it: start Claude Code with the plugin loaded for that session only, then run the interview on a new folder.

```sh
claude --plugin-dir /Users/vs/workspace/alpha
/alpha:new-project ~/code/my-new-project
```

Optional: to stop Claude Code asking before each alpha CLI call during the interview, add `"Bash(/Users/vs/workspace/alpha/bin/alpha *)"` to `permissions.allow` in `~/.claude/settings.json` (for an installed plugin, use the `bin/alpha` path the prompt shows).

Install it for every session later with `claude plugin marketplace add /Users/vs/workspace/alpha`, then `claude plugin install alpha@alpha-local`. `claude plugin validate .claude-plugin/marketplace.json` checks the manifests.

Kit tests: `uv run pytest` runs the fast suite. `uv run pytest -m slow` also bootstraps real projects with uv and pnpm (needs both installed and network access).

### Live run findings (2026-10-20, Claude Code 2.1.303)

A scripted `claude -p --plugin-dir` run answered the `web-ts-plus-python-api` scenario (with `review.max_lines = 100` instead of the scenario's observability override, and "no" to making it a default). It reached a generated, bootstrapped and committed project in 15 turns.

- Verified: four grouped commits (docs, chore, build(api), build(web)) with only the session's trailer; `uv run pytest`, `pyright`, `pnpm vitest run` and `pnpm tsc --noEmit` pass; nothing kit-specific at the root and no `src/` placeholders; decision 0004 and `docs/principles.toml` record `max_lines = 100`; the kit's `defaults/` stayed unchanged.
- Hooks in the generated project: `git commit --no-verify` is blocked; `# type: ignore` gets an "ask" (a denial in `-p` mode, where nobody can answer it); a source file without a test makes Stop block (three times, then it gives up with a message); edited files are formatted and linted.
- Claude Code always asks before Write/Edit under `.claude/` (allow rules and PreToolUse "allow" can't pre-approve it), which cost an approval per save. The skills now save through `alpha answers write <target> --json '…'` instead: one-line Bash calls, so at most a Bash approval with "don't ask again". A multi-line heredoc form was still prompted; the one-line form ran without a prompt in a follow-up run.
- A skill's `allowed-tools` seemed to pre-approve the alpha CLI only in the turn the skill was invoked in (one probe each way); later turns may ask for each `bin/alpha` call unless you add the optional rule above.
- Without a git identity, `alpha commit-skeleton` now stops and says how to set one instead of committing as `you@host.local`.
