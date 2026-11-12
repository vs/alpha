# 0010. Weekly manual updates

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

One toolchain (uv) plus the mise-pinned check tools drift. The kit default is Dependabot, but with no CI nothing would check its pull requests.

## Decision

Updates: manual (kit default dependabot), weekly, after a 7-day cooldown from each release.

## Consequences

Someone runs the updates weekly with uv and mise, and checks them locally with mise run check before committing; a new dependency still needs its row in docs/dependencies.md. Not made a default for future projects.
