# 0008. No CI, plugin package

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

alpha is published as a Claude Code plugin through its own marketplace on GitHub (vs/alpha); nothing is deployed. The kit default is GitHub Actions.

## Decision

CI: none (loosens build-hosting-upfront). No environments. alpha builds into a package (the plugin, published through its marketplace); no hosting.

## Consequences

Nothing checks a push remotely: mise run check (and the commit hooks) are the only gate, so run them before every commit. Not made a default for future projects.
