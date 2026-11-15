# 0035. One process doc and one specification doc

Date: 2026-11-15
Status: accepted
Kind: product

## Context

The user: "there are multiple alpha-related files at docs directory. Tell me if it's possible to merge them into a single file related to the development process only and then leave specification related files to some other files as a user decides". On the options Claude laid out, the user chose: "let's use contributing" for the process, and for the specification "A, but let's use docs/specification.md for the whole project specification and then put features specification into docs/specs/... directory". Asked one question at a time, the user kept docs/design-language.md and docs/glossary.md as their own files, and put the migration and experiment rules in CONTRIBUTING.md with the storage choices in the specification.

Claude's choice, open to correction: docs/dependencies.md stays separate, because the Stop hook checks that this file changed when a lockfile did, and inside a shared file any edit would pass; docs/adoption.md stays separate as a temporary plan.

## Decision

A generated or adopted project's development process is in CONTRIBUTING.md: setup, checks, commit convention, testing, docs mapping, branching, and now the layout and components, build, CI and hosting, releases, secrets and protected paths, and the migration and experiment rules.

The project's specification is one file, docs/specification.md, rendered from the answers: value proposition, target users, requirements, the spec areas not settled yet, architecture, errors, auth, UI and accessibility, data storage, performance and observability, each where it applies. Feature specs stay in docs/specs/.

docs/principles.toml, docs/decisions/, docs/dependencies.md, docs/design-language.md, docs/glossary.md and docs/adoption.md keep their paths. product.md, architecture.md, build.md, security.md, releases.md, ui.md, data.md, performance.md and observability.md are no longer written.

The design is in docs/specs/2026-11-15-one-process-doc-one-spec-doc.md.

## Consequences

- Requirements trace to rows of docs/specification.md.
- Existing projects keep their files; nothing migrates. alpha's own docs move by hand.
- An adopted repo that already has a CONTRIBUTING.md or docs/specification.md gets a proposal to merge by hand, as for any file it already has.
