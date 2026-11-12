# 0012. Semver tags with GitHub releases

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

Plugin users update through the marketplace and read release notes on GitHub. The repo already tags vX.Y.Z on main and has GitHub releases, but no CHANGELOG.md; the kit default changelog is a file.

## Decision

Scheme semver, changelog github-releases (kit default file), scope repo. Process: a chore: Release X.Y.Z commit bumps plugin.json, pyproject.toml, src/alpha/__init__.py and uv.lock; tag vX.Y.Z on main and publish a GitHub release with its notes.

## Consequences

A breaking change to answers, recipes or the CLI is a major version (minor while 0.x) and its release notes say how to migrate. v0.2.0, v0.4.1 and v0.4.2 have tags but no GitHub release yet. Not made a default for future projects.
