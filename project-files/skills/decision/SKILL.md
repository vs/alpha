---
name: decision
description: Record a decision in this project's decision log (docs/decisions/). Use whenever the user settles a question, you make a choice on an ambiguous requirement, a check needs an exception in one place, a principle is loosened or dropped, a review finding is accepted, or an earlier decision is replaced.
---

# Record a decision

The decision log in `docs/decisions/` is how this project remembers why it is the way it is. Every agent reads the records that bear on a change before making it, so a decision that isn't recorded is a decision the next agent can't follow. The interview wrote the first records; this skill writes every later one, in the same format.

## 1. Number and file name

- Find the highest number among `docs/decisions/NNNN-*.md` and add one; write it with four digits (`0013`).
- Make a slug from the title: lowercase words joined by `-`, letters and digits only (`use-openapi-for-the-api`).
- The file is `docs/decisions/NNNN-<slug>.md`.

## 2. Format

Write exactly this shape, with today's date:

```markdown
# NNNN. <Title>

Date: YYYY-MM-DD
Status: accepted

## Context

<What prompted the decision: the question, the constraint, who asked.>

## Decision

<What was decided, concretely enough to check a change against it.>

## Consequences

<What this rules in or out, and what must change because of it.>
```

Extra header lines go right under `Status:`, one per line:

- `Kind: product` when the record settles what the product does or for whom: its users, scope, acceptance checks, UI or accessibility. `Kind: technical` for everything else: stack, libraries, structure, tooling, thresholds.
- `Supersedes: NNNN` when this record replaces an earlier one.
- `Principle: <id> (<loosen|drop|tighten>, scope <project|component:name>)` when it changes a principle.
- `Accepts: F-xxxxxx` for each review finding that stands: one the user accepted, or one you disproved. A disproof says in `## Decision` why the finding is wrong, concretely enough for the next review to check; a finding on a risk path needs the user's "accept F-xxxxxx" first.

When the user decided, use their own words. When you made the choice, say so in `## Context` and give the reason, so the user can correct it later. The title names the choice ("Use OpenAPI for the api contract"), not the question.

## 3. Replacing an earlier decision

When the new record replaces an earlier one, add `Supersedes: NNNN` to the new record, and change the earlier record's `Status: accepted` line to `Status: superseded by NNNN`. That status line is the only edit ever made to an old record; its text stays as it was, so the history reads true.

Supersede a `Kind: technical` record yourself when the change needs it: say in `## Context` why the old decision no longer holds, and tell the user what you replaced. A `Kind: product` record, a record with a `Principle:` line, or one with no `Kind:` line needs the user's agreement first; quote it in `## Context`.

## 4. Changing a principle

Loosening, dropping or tightening a principle also changes `docs/principles.toml`, the source of truth the hooks read: update the principle's `active`, `components` or `params`, and set its `override_decision` to the new record's path. Editing that file asks the user first; that's intended.

Then bring the principle's line under `## Principles` in CLAUDE.md in step: end it with a space and `(overridden: see <record path>)`, replacing any earlier one, or remove the line when the principle is now off for the whole project.

## 5. Commit

Commit the record together with the change it explains, following the project's commit convention (see CLAUDE.md and CONTRIBUTING.md). A record on its own is a `docs:` commit.
