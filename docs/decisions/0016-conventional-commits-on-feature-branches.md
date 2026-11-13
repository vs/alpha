# 0016. Conventional commits on feature branches

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

One maintainer and Claude commit; 48 of the last 50 commits already follow conventional commits (the other two are merges), with scopes hooks, recipes, defaults and spec in use.

## Decision

Convention: conventional. Scopes: alpha, hooks, recipes, defaults, spec. Branching: feature-branches merged into main. Git hooks: alpha sets core.hooksPath (no hook manager found).

## Consequences

The commit-msg hook rejects a header that is not type(scope): description with a 50-char imperative description, or body lines past 72; merge, revert and fixup commits pass. Existing history stays as it is.
