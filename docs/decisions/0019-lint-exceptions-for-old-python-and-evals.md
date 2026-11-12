# 0019. Lint exceptions for old Python and the eval runner

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

Adoption step `p2-ruff-rules-alpha` turned on the kit's ruff rules for alpha, including PLC0415 (imports at the top) and BLE001 (no catch-all except). Four places break them on purpose. Claude made this choice while carrying out the step.

- The hooks must run on any `python3`, including 3.9, long enough to print how to upgrade. `tomllib` is absent before 3.11, so a top-level import would crash before the version check.
- The eval runner reports a crashing scenario, check or reviewer probe in its summary and goes on with the rest; `test_a_crashing_scenario_does_not_stop_the_run` holds it to that.

## Decision

These lines keep their exception, each as a `# noqa` naming the one rule, with its reason:

- `project-files/hooks/_common.py`, PLC0415: the `tomllib` import in `load_principles`.
- `project-files/hooks/session_start.py`, PLC0415: the `tomllib` imports in `principles_problem` and `_lenient_principles`.
- `src/alpha_evals/run.py`, BLE001: `_safe` and the reviewer probe in `run_scenario`.
- `src/alpha_evals/__main__.py`, BLE001: the per-scenario loop.

## Consequences

Any other late import or catch-all except fails ruff. Once the hooks require Python 3.11, the `tomllib` imports move to the top and their exceptions go.
