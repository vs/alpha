# 0020. Check principles.toml at load, typed model later

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

Adoption step `p4-typed-principles` found that `load_project_principles` returned raw TOML that about 23 functions index as `dict[str, Any]`, so a hand edit gave a traceback and the CLI's blanket `except KeyError` blamed the file for any missing key. Claude chose the smaller fix while carrying out the step: moving every reader onto a typed model is a rewrite of the generate, update, gitops and baseline code paths, larger than the step's failure.

## Decision

`load_project_principles` (in `src/alpha/generate.py`) checks the fields alpha's commands read: `project.slug`; each component's `name`, `path`, `stack`, `commands` (with `setup` and `test`) and `lockfiles`; each baseline's `id`. A problem stops with the field, the component and how to restore the file. A `KeyError` after that is a bug, and the CLI shows it as one. The readers keep indexing the checked dicts.

## Consequences

A command that starts reading a new field of principles.toml adds it to `_principles_problem` in the same change. The typed model stays open: parse principles.toml into dataclasses once, and pass those to the readers instead of dicts.
