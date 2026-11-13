# 0013. Versioned JSON and TOML files

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

alpha stores answers in each project (project.json, schema 1), the user layer in ~/.config/alpha/ and baseline files; they outlive the plugin version that wrote them.

## Decision

Storage: JSON and TOML files. Migration tool: none today; answers refuses any schema but 1, and skills treat a missing area as pending. No ML.

## Consequences

Bumping project.json schema needs an upgrader that rewrites older files, with tests, before release; until then a shape change must stay backward compatible. There are no migration files, so the append-only rule has nothing to guard.
