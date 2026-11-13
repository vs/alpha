# 0021. No CI: the checks run locally before each commit

Date: 2026-11-13
Status: accepted
Kind: technical
Supersedes: 0018
Principle: build-hosting-upfront (loosen, scope project)

## Context

In the adoption interview (2026-11-12), Claude recommended GitHub Actions for CI (Q16). The user answered "q16 none". Claude then suggested the reason for loosening the principle (Q18): "`mise run check` runs locally before each commit, and the slow tests and evals need real toolchains and paid tokens that CI shouldn't spend." The user answered "Follow the recommendations".

Record 0018 kept that reason but not the user's words, which a record that changes a principle must quote. On 2026-11-13 the user agreed to this record replacing it ("3. Yes").

## Decision

Loosen build-hosting-upfront for the whole project: alpha has no CI. `mise run check` runs every check locally, and the Stop hook runs the Stop checks before Claude finishes. The slow tests (`uv run pytest -m slow`) and the evals (`bin/alpha-evals run`) run by hand when a change needs them.

## Consequences

Nothing checks a push or a pull request on GitHub, so a branch is only as checked as the last local `mise run check`. The principle's `override_decision` in docs/principles.toml and its line in CLAUDE.md point to this record.
