# 0023. Exhaustive testing is an opt-in principle

Date: 2026-11-13
Status: superseded by 0028
Kind: product

## Context

The user asked (2026-11-13): "SQLite is knows as an extremely well tested
software. I want to embed the testing principles of SQLite into
alpha-managed projects but make it optional. So for example for some project
I can ask alpha to setup this extremely well tested approach and alpha would
set it as a principle and then enforce that in the project."

The rest is Claude's choice, open to correction:

- How it is switched on: one yes/no answer in the testing round, not a new
  area, as §8a D3 of the spec does for the other testing tunable.
- Its scope: the whole project, not one component. The diff-coverage
  threshold it raises is one number per project.
- Which of SQLite's practices carry over. Its four separate test harnesses
  and its release checklist don't fit a project of any size, so they are
  left out.
- No fuzzing, property-testing or mutation-testing tool is added to the
  recipes. Each is a dependency whose pick depends on what the project
  parses; the project adds it when its first test needs it.

## Decision

`testing.exhaustive` (true or false, default `defaults.testing.exhaustive`,
which is false) switches on the principle `exhaustive-testing` for every
component. Its statement, from <https://www.sqlite.org/testing.html>: every
branch taken both ways, every failure path forced by an injected failure,
fuzz or property-based tests for whatever reads outside input, each limit
tested at, just below and just above its value, a failing test before each
bug fix, invariants asserted in the code, tests run on the build that ships.

It is enforced in two ways:

- The principles reviewer checks every change against it, as it does any
  active principle.
- The pull-request coverage gate becomes `diff-cover --fail-under=100
  --branch-coverage`: every changed line, and both sides of every changed
  branch where the coverage report has branch data. The Python recipe's
  coverage command gains `--cov-branch` for that. An answer that sets
  `diff_coverage` below 100 together with `exhaustive` is refused.

## Consequences

- A project that doesn't opt in changes in one place: its Python coverage
  run also records branches, which the gate ignores without
  `--branch-coverage`.
- Stable Rust reports no branch coverage, so a Rust component's gate is
  every changed line; its branches are the reviewer's to check.
- A project with `build.ci = "none"` has no coverage gate, exhaustive or
  not; there the reviewer alone enforces the principle.
- Mutation testing, which SQLite uses to prove its coverage means something,
  has no mechanical check yet.
- The interview evals don't cover the new question.
