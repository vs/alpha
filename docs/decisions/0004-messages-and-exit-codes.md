# 0004. Messages and exit codes

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

alpha errors reach a developer at the terminal or Claude running a skill, which relays the fix.

## Decision

alpha uses message-and-exit-code: alpha: <problem> and its fix on stderr, non-zero exit. Categories: validation, not-found, conflict, unavailable, internal (the kit defaults).

## Consequences

Every error names what went wrong and the next step to fix it, so a skill can act on it without guessing.
