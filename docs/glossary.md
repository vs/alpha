# Glossary

Use these names in code, docs and UI alike.

| Term | Meaning |
|---|---|
| adoption step | One item of an adopted repo's compliance plan, done only when its acceptance conditions hold. |
| area | One topic alpha settles and saves in project.json (identity, components, ...), with its own skill: a setup area or a spec area. |
| baseline | The legacy findings of one check in an adopted repo, per file and rule; only new findings fail and it only shrinks. |
| component | One part of a project with its own folder, kind, stack and checks; also a commit scope. |
| design language | The one look a project declares for all its visuals (diagrams, charts, images, UI): optional, and enforced by the reviewer only when defined. |
| feature spec | A feature's requirements, the test that proves each acceptance check, and its plan, in docs/specs/; the user approves it before any code. Not the kit's design spec in docs/superpowers/specs/. |
| kit | The defaults, recipes, registry and templates alpha ships, which every project starts from. |
| override | A project's recorded change to a principle (tighten, loosen or drop), with its reason. |
| playbook | The steps /alpha:go follows for one kind of task (feature, bug fix, refactoring, ...), kept in the plugin, not copied into projects. |
| principle | A rule in docs/principles.toml, enforced by a hook, a check or the principles reviewer. |
| recipe | How a component on a stack is set up and checked: the kit's own, one drafted for a project, or one adopted from a repo's tools; proven before use. |
| setup area | An area the interview settles because alpha needs it to wire the tooling: identity, components, testing, documentation, build, security, dependencies, releases, git, agent workflow. |
| spec area | An area that describes the product (architecture, errors, design language, UI, observability, data, accessibility, performance); it starts open and /alpha:go settles it when the work needs it. |
