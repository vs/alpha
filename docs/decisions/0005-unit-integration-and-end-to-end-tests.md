# 0005. Unit, integration and end-to-end tests

Date: 2026-11-12
Status: accepted
Kind: technical

## Context

The risk is in subprocess calls, file merges and stored state, and in whole flows (interview, generate, adopt, update) users drive through bin/alpha and the skills.

## Decision

alpha: unit, integration (the real-toolchain tests now marked slow) and end-to-end (whole flows from R1-R7). Diff coverage 80% (kit default).

## Consequences

A test covering an acceptance check names its requirement id (R1-R7). Today tests are flat under tests/ and few name a requirement; moving them under tests/<level>/ and linking them is part of the adoption plan. Diff coverage applies once the recipe has a coverage command.
