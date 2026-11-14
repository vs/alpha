# 0032. Setup first, specification later

Date: 2026-11-15
Status: accepted
Kind: product

## Context

Using alpha on mental, the user found that the interview "goes deep into specification details for new project or component, when even I don't realize all the details and I'd require quite a lot of research to specify those details. I think this is a mistake in alpha's design. I believe that alpha has to be the tool that takes care of the application development lifecycle, including updating the docs, running tests and reviews, configuring CI, checking typos, etc. But the part where I actually work on a specification must be out of alpha:new-project or alpha:adopt cycles. I should use alpha:go instead in order to incrementally update the specification."

The user agreed to each part ("yes to all"): which areas are setup and which are specification, an explicit `open` status, `/alpha:go` settling open areas, adopt's plan holding no specification work, and no migration for existing projects. On the last: "when I update the plugin, let's just update all the necessary files manually in both repositories as alpha installed into alpha and mental only".

Claude's choices, open to correction: requirements, target users and auth stay fields of their setup areas, allowed empty; the principles an open area gates name it in the catalog (`settled_by`).

## Decision

The interview of `/alpha:new-project` and `/alpha:adopt` settles only the setup areas: identity (name, slug, value proposition, license, copyright), components, testing, documentation, build, security, dependencies, releases, git and agent workflow. The spec areas (architecture, errors, design language, UI, observability, data, accessibility, performance) start `open`. An open area needs no decision, writes no doc of its own, is listed under "Not settled yet" in docs/product.md, and keeps the principles it gates off.

`/alpha:go` settles an open area on request (its Specify playbook) and before a feature that touches it, through `/alpha:extend`. Adopt's compliance plan holds only tooling and principle work; findings about specification content are reported as `/alpha:go` tasks.

The design is in docs/specs/2026-11-15-setup-first-spec-later.md.

## Consequences

- The design spec's anti-goal "skipping areas to save time" no longer covers the spec areas; they are deferred on purpose, not skipped.
- R1's acceptance check changes: setup areas done, spec areas open.
- Existing projects keep every area done and change nothing; alpha's and mental's copied files are updated by hand.
- Not verified until the end of the work: a live interview.
