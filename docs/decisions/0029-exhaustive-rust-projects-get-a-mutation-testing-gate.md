# 0029. Exhaustive Rust projects get a mutation-testing gate

Date: 2026-11-14
Status: accepted
Kind: product

## Context

The user asked: "make alpha's Rust defaults: workspace, branch coverage, mutation testing". This record is the third of the three. Decision 0023 said: "Mutation testing, which SQLite uses to prove its coverage means something, has no mechanical check yet", and chose to add no fuzzing, property-testing or mutation-testing tool to the recipes. The user's brief for this change: for Rust components, add a gate whenever `testing.exhaustive` is on, using cargo-mutants pinned like the other cargo tools; run it in pull-request CI on the diff, with a timeout multiplier; a missed mutant fails, a timed-out one counts as caught, a deliberate skip is `#[mutants::skip]` with the reason in a comment that the reviewer checks; add `ci:mutants` and one sentence to the principle; include it in `mise run ci` locally when it's run on a diff; leave Python out; keep 0023's other choice, no fuzzing or property-testing tool.

Claude's choices, open to correction:

- The command. `cargo mutants --in-diff pr.diff --in-place --timeout-multiplier 3 || [ $? -eq 3 ]`. cargo-mutants 27.1.0 exits 2 on a missed mutant and 3 when one timed out and none was missed, so exit 3 passes.
- The override. `defaults.testing.mutants` (true) and the answer `testing.mutants`; it only matters under exhaustive testing, and `true` without it is refused.
- Locally. `mise run ci` gets a `check:mutants:<component>` task per gated component. It runs when `ALPHA_BASE` names the base branch, as the other diff checks do, and is skipped in CI, where the component's own job has the toolchain and runs the step.
- Where the skip rule lives. The Rust recipe's `mutants-skips` stack rule and one sentence in the principles reviewer's brief.

## Decision

A recipe may name a `mutants` command. When the project is tested exhaustively and `testing.mutants` isn't false, each component whose recipe has one gets:

- a `mutants` step in its pull-request CI job: `git diff --relative "origin/<base>"...HEAD > pr.diff`, then the command, run in the component's folder. The diff names files from the root of the tree cargo-mutants mutates: the component's folder, hence `--relative`, or the repository's for a member of a Cargo workspace (decision 0027), where `--relative` is left out. A diff from the other root matches no file, and cargo-mutants then exits 0 with nothing checked; the principles reviewer caught that, and a slow test now runs the gate for a crate in a subfolder;
- a `check:mutants:<component>` task among the dependencies of `mise run ci`.

The Rust recipe names the command above and installs cargo-mutants 27.1.0 in bootstrap and CI. A mutant that survives fails the check; one whose tests time out counts as caught; one that can't be killed on purpose is skipped with `#[mutants::skip]`, with the reason in a comment the reviewer checks like any suppression.

The `exhaustive-testing` principle gains the sentence "Every changed line's mutants are caught by a test." and `ci:mutants` in `checked_by`.

## Consequences

- An exhaustive Rust pull request runs the tests once per mutant of its changed lines, in the component's 30-minute job. A large change may need splitting.
- Python and TypeScript components get no gate: their recipes name no command. mutmut would be the equivalent for Python; for them the principle's new sentence is the reviewer's to check.
- `#[mutants::skip]` needs the `mutants` crate; the project adds it with its first skip.
- `pr.diff` and `mutants.out*/` are ignored, so CI's unchanged-tree step still passes.
- A project with `build.ci = "none"` has only the local task.
- Not verified: the step on GitHub.
