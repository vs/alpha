# 0009. Local CLI, no secrets or auth

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

alpha runs on the user machine and is not deployed; the evals use the claude CLI login, which alpha never handles.

## Decision

No secret store (nothing deployed; local .env files suffice). Auth: none. No extra protected paths.

## Consequences

Claude cannot edit .env files, keys or lockfiles (always protected); the betterleaks check blocks a committed secret. Baseline-output fixtures stay editable so they can be re-recorded.
