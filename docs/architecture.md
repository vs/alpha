# Architecture

## Layout

Layout: single.

## Components

| Name | Path | Kind | Stack | Traits |
|---|---|---|---|---|
| alpha | . | cli | alpha-python | network_calls, persisted_data, nontrivial_logic |

Components do not communicate with each other.

## Tool choices

- alpha-python: the stack's own toolchain. Commands: `uv sync`, `uv run pytest`, `uv run ruff check src tests project-files`, `uv run ruff format src tests project-files`, `uv run ruff format --check src tests project-files`, `uv run pyright` (less proven: recipe drafted for this project)

## Responsibilities

| Component | Responsibility | Calls |
|---|---|---|
| alpha | Turns interview answers into an enforced project (generate, adopt, update) and checks the answers, recipes, baselines and adoption steps that drive it. | - |

## Contracts

No contracts: components don't call each other.

## Errors

Every error a user sees says what went wrong and how to fix it.

| Component | Format | Meaning |
|---|---|---|
| alpha | message-and-exit-code | A message on stderr and a non-zero exit code. |

Categories:

- validation
- not-found
- conflict
- unavailable
- internal
