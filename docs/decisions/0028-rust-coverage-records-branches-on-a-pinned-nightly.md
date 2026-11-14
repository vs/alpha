# 0028. Rust coverage records branches on a pinned nightly

Date: 2026-11-14
Status: accepted
Kind: product
Supersedes: 0023

## Context

The user asked: "make alpha's Rust defaults: workspace, branch coverage, mutation testing". This record is the second of the three. Decision 0023 made exhaustive testing an opt-in principle and said: "Stable Rust reports no branch coverage, so a Rust component's gate is every changed line; its branches are the reviewer's to check." The user's brief for this change: "Update decision 0023's consequences, or supersede it, so it no longer says Rust branches are left to the reviewer." An accepted record's text isn't edited, so this record supersedes 0023 and carries its decision over with that one consequence changed. Its mutation-testing consequence changes in decision 0029.

The user's brief: keep the pinned stable toolchain for build, test, lint and format; run only the coverage command on a pinned, dated nightly; record the date once, in the recipe; install the nightly in bootstrap and CI; prove on real tools that diff-cover reads the branch data, and stop if it doesn't.

It does. On nightly-2026-11-10 with cargo-llvm-cov 0.9.1, `--branch --cobertura` marks the line of an `if` taken one way as `branch="true" condition-coverage="50% (1/2)"`, and diff-cover 11.0.1 fails it with `--branch-coverage` while passing it without. A slow test repeats this on each run.

Claude's choices, open to correction:

- The nightly: `nightly-2026-11-10`, the newest tried. It is named once, in the recipe's new `[vars]` table (`coverage_toolchain`), and the recipe's bootstrap, coverage command and CI step refer to it as `${coverage_toolchain}`.
- CI installs it with a second use of `actions-rust-lang/setup-rust-toolchain` (`override: false`, no cache), so the stable toolchain of `rust-toolchain.toml` stays the default.

## Decision

Exhaustive testing, as 0023 decided: `testing.exhaustive` (true or false, default `defaults.testing.exhaustive`, which is false) switches on the principle `exhaustive-testing` for every component. Its statement follows <https://www.sqlite.org/testing.html>. The principles reviewer checks every change against it, and the pull-request coverage gate becomes `diff-cover --fail-under=100 --branch-coverage`. An answer that sets `diff_coverage` below 100 together with `exhaustive` is refused. No fuzzing or property-testing tool is added to the recipes; the project adds one when its first test needs it.

New here: every Rust project's coverage run records branches, as Python's does. The Rust recipe's coverage command is `cargo +<nightly> llvm-cov --branch --cobertura --output-path coverage.xml`, and nothing else runs on the nightly. The gate reads the branches only when `testing.exhaustive` is on.

## Consequences

- A Rust component's exhaustive gate now covers both sides of every changed branch, like Python's and TypeScript's.
- A project that doesn't opt in changes in one place per stack: its Python and Rust coverage runs also record branches, which the gate ignores without `--branch-coverage`.
- An implicit `else` counts: an `if` without one, taken only when true, leaves its closing line uncovered, so the line gate reports it too.
- The nightly's date moves with a kit release: pick a newer date in `recipes/rust.toml`, rerun `uv run pytest -m slow -k rust`, release. `alpha update` then writes the new date into each project's CI workflow; bootstrap reads it from the kit. The weekly toolchain check doesn't watch it.
- A project with `build.ci = "none"` has no coverage gate, exhaustive or not; there the reviewer alone enforces the principle.
- The interview evals don't cover the exhaustive question.
- Not verified: the workflow on GitHub (the second toolchain install).
