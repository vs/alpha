# 0018. Override build-hosting-upfront

Date: 2026-11-12
Status: accepted
Principle: build-hosting-upfront (loosen, scope project)

## Context

mise run check runs locally before each commit, and the slow tests and evals need real toolchains and paid tokens that CI should not spend.

## Decision

Loosen build-hosting-upfront for project.

## Consequences

See docs/principles.toml for the resulting parameters.
