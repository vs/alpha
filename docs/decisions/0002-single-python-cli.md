# 0002. Single Python CLI

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

alpha is one Python package (src/alpha, src/alpha_evals) driven through bin/alpha and the plugin skills; the survey found one candidate at the root.

## Decision

One component, alpha: kind cli, stack alpha-python (adopted, extends the kit python recipe), path . (single layout). Traits: network calls (subprocesses), persisted data (project.json, user layer, baselines), non-trivial logic; no UI, not deployed, no ML.

## Consequences

One toolchain to maintain (uv, Python 3.11+). Subprocess calls need timeouts and failure paths; project.json and the user layer need a migration path on schema change. The recipe runs the commands mise.toml already runs; deptry and coverage are not set up yet.
