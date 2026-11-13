# 0024. The full test suite runs before main, not at every Stop

Date: 2026-11-13
Status: accepted
Kind: product

## Context

The Stop hook reran each changed component's full test suite whenever any
file in the component differed from its last run. In this repo that is every
turn: the component is the whole repository, so a one-line doc edit, or an
answer to a question after an edit, started the 8-minute suite again. A run
Claude had just made itself didn't count, and sessions queued behind each
other's suites.

The user (2026-11-13): "Stop hooks running too often and that blocks any
progress, everything is too slow with these hooks on alpha. Let's reconsider
some decisions, so things work smarter and full test suite runs only when
it's actually needed and not on every minor event". Offered three timings
(at merge as a setting, at commit, at Stop but smarter), the user chose "At
merge, as a setting", and said yes to running alpha's own suite in parallel.

Claude's choices under that answer: the setting's name and place
(`testing.run`, in the testing round), how a pass is recorded (a command
Claude runs, not a guess from its shell history), and that a principles file
without the setting keeps the old timing.

## Decision

`testing.run` says when alpha's hooks run a component's full test suite. It
is asked in the testing round and defaults to `defaults.testing.run`, which
is `at-merge`.

- `at-merge`: the Stop hook runs the type check and structure check, not
  the tests. Before Claude's work reaches main (a push to main, or `gh pr
  merge`), the command guard requires that the test suite of every component
  the checkout changed since it left main has passed on the files as they
  are now. `python3 .claude/alpha/hooks/stop_checks.py tests` runs those
  suites and remembers a pass until the component's files, its test
  command or its baselines change. A failure isn't remembered, so the next
  run tries again, and the command isn't held to the Stop hook's time
  limits.
- `at-stop`: the Stop hook runs the suite at every turn's end, as before,
  and there is no gate at the merge.

A principles file with no `testing.run` behaves as `at-stop`.

alpha's own suite runs in parallel (pytest-xdist, `-n 4`). With 12 workers
it took under 2 minutes, but a test that commits with git failed about once
in 15 runs of `tests/integration/test_update.py` ("unable to create temporary
file: Invalid argument"), and once in 20 with 6; with 4 it passed 15 of 15.
The cause isn't found.

## Consequences

- A failing test is found when Claude runs the tests itself or at the
  checkpoint, no longer at the end of each turn. The "source changed with no
  test change" flag, the type check and the repository checks still run at
  Stop.
- The gate binds Claude only, like the review gate; people push by hand.
- A project with `build.ci = "none"` and `at-merge` has its tests enforced
  at that one checkpoint and nowhere else.
- Existing projects get `at-merge` when `alpha update` upgrades them to this
  kit (decision 0022), so the kit's version must be bumped for them to see
  it. Spec §8 changes to match.
