# 0007. README as user docs

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

Users meet alpha through the README and three skills; developers through CLAUDE.md. The kit usual CLI globs match nothing here.

## Decision

User docs live in README.md (kit default). Mapped: src/alpha/cli.py and bin/** to README.md or CLAUDE.md; skills/new-project, skills/adopt and skills/extend to README.md. Decision records start at 0001 in docs/decisions/.

## Consequences

A change to the CLI or a user-invoked skill must update the README (or CLAUDE.md for the CLI), or the Stop hook blocks it.
