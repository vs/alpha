# Glossary

Use these names in code, docs and UI alike.

| Term | Meaning |
|---|---|
| adoption step | One item of an adopted repo's compliance plan, done only when its acceptance conditions hold. |
| area | One topic of the interview (identity, components, ...), settled by its own skill and saved in project.json. |
| baseline | The legacy findings of one check in an adopted repo, per file and rule; only new findings fail and it only shrinks. |
| component | One part of a project with its own folder, kind, stack and checks; also a commit scope. |
| kit | The defaults, recipes, registry and templates alpha ships, which every project starts from. |
| override | A project's recorded change to a principle (tighten, loosen or drop), with its reason. |
| principle | A rule in docs/principles.toml, enforced by a hook, a check or the principles reviewer. |
| recipe | How a component on a stack is set up and checked: the kit's own, one drafted for a project, or one adopted from a repo's tools; proven before use. |
