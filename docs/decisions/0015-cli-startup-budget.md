# 0015. CLI startup budget

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

Skills call bin/alpha many times per interview and hook, so a slow start adds up; the load is one developer on a laptop.

## Decision

alpha: startup < 200 ms (kit default for a CLI), measured by an end-to-end pytest test timing bin/alpha --help, run by mise run check. Today it starts in about 60-70 ms.

## Consequences

Breaking the budget needs a fix or a decision record. The timing test does not exist yet; it is an adoption step.
