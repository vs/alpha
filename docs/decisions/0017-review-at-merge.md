# 0017. Review at merge

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

Work happens on feature branches verified once when finished; a review per task would slow small changes, and the hooks already check every edit.

## Decision

Review mode at-merge (kit default); max_lines 200 and max_files 5 recorded for batched mode; no extra risk paths beyond the kit ones.

## Consequences

Claude stops for the principles reviewer before pushing to main or merging a pull request, and cannot finish with open findings.
