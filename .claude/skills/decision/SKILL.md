---
name: decision
description: Record a decision in this project's docs, where it takes effect. Use whenever the user settles a question, you make a choice on an ambiguous requirement, a check needs an exception in one place, a principle is tightened, loosened or dropped, a review finding is accepted or disproved, or an earlier choice changes.
---

# Record a decision

This project keeps no separate record of decisions: a decision changes the docs that say how things are, and git history keeps when and why. Every agent reads `docs/alpha/specification.md` and `CONTRIBUTING.md` before changing anything, so a decision that isn't written there is a decision the next agent can't follow.

## 1. Where it goes

| The decision | Where it goes | Who agrees |
|---|---|---|
| What the product does: a requirement, a user-facing behavior, a product area's answer | `docs/alpha/specification.md`, through the answers when alpha writes that part (`/alpha:update <area>`), else by editing it; a feature's own choices go in its spec in `docs/alpha/features/<date>-<feature>/` | The user, always |
| How the work is done: a tool, a convention, a process step | `CONTRIBUTING.md`, through the answers when alpha writes that part (`/alpha:update <change>`), else by editing it | Claude, with the reason in the commit message |
| A principle tightened, loosened or dropped | An override in the answers (below), which alpha lists in CONTRIBUTING.md's Overrides | The user, always |
| A check skipped or loosened in one place, or a baseline loosened | A row in CONTRIBUTING.md's Exceptions table (below) | The user for a risk path, else Claude with the reason |
| A review finding accepted or disproved | An `Accepts:` trailer on a commit (below) | The user for a finding on a risk path, else Claude |

A choice that only one change needs, and that no later change must follow, needs nothing beyond the commit message.

## 2. Writing it

**A part alpha writes.** docs/alpha/specification.md and CONTRIBUTING.md are generated from `.claude/alpha/project.json`; change those parts through the answers, never by editing the generated text: a product area or a component or a process answer with `/alpha:update <request>` (it updates the answers and merges the docs). Add your own sentences or sections anywhere else in those files; updates keep them.

**An override.** Save it with `/alpha:update`, which writes `{"principle", "scope", "change", "params", "reason"}` to `overrides` in the answers: `scope` is `"project"` or `"component:<name>"`, `change` is `"tighten"`, `"loosen"` or `"drop"`, and `reason` is required for `loosen` and `drop`. `alpha update` then changes `docs/alpha/principles.toml` and lists it under Overrides.

**An exception.** Add a row under the header of CONTRIBUTING.md's `## Exceptions` table: the path in backticks, the check or rule in backticks (a lint code, the type checker's ignore comment, a baseline id such as `typecheck:api`), and the reason it doesn't hold there. The hooks and the pull request check look for a row naming the path or the check; a row already there before the branch doesn't count for a new baseline growth.

**A finding.** Add a trailer to the commit that settles it, or to an empty commit (`git commit --allow-empty`): `Accepts: F-xxxxxx <why it stands or why it's wrong>`, one line per finding. The principles reviewer judges each one at the next review before main; a finding on a risk path is accepted only by the user replying `accept F-xxxxxx`.

## 3. Changing an earlier choice

Change the doc, the override or the row in place; git keeps the old one. Say what changed and why in the commit message. A product choice, or a principle's override, changes only with the user's agreement: quote it in the commit message.

## 4. Commit

Commit the docs change together with the change it explains, following the project's commit convention (CLAUDE.md, CONTRIBUTING.md). A docs change on its own is a `docs:` commit.
