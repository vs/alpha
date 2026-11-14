# 0030. Adopt generates the skeleton of a component with no manifest

Date: 2026-11-14
Status: accepted
Kind: product

## Context

The user ran `/alpha:adopt` on a repo that held docs and no code: the interview settled four Rust components, none with a build file. Spec §5b gave every component an adopted recipe, which runs the repo's own tools, so there was nothing to attach to. The session stopped, asked a three-way question, and then wrote the kit's Rust templates by hand before going on. The user asked: "I want to update this project so it handles such cases without major interruption just by asking a user to generate a proper project structure for a given component".

Claude's choices, open to correction:

- What counts as "no project structure". In the interview: the component's folder is missing or holds only docs. Code without a manifest still gets an adopted recipe and baselines. In the CLI: the component is on a kit or drafted recipe and none of the recipe's `manifests` is in its folder; a manifest the repo already has is never written over.
- No new answer field. The component's `stack` already says it: a kit or drafted recipe means alpha's skeleton, an adopted recipe means the repo's tools.
- Commits. Several new members of one workspace go into one commit, as `commit-skeleton` does, because the workspace's root files list every member. This also holds for `alpha update`.

## Decision

In an adoption, a component with no project structure yet (its folder is missing or holds only docs) is not given an adopted recipe. The interview asks once per such component whether alpha generates its skeleton. On yes, its `stack` is the kit's recipe, or one drafted and proven as for a new project.

`alpha adopt apply` then writes that recipe's templates beside whatever the folder holds, and names the component under `New components`. `alpha bootstrap --capture-baselines` installs its toolchain and runs its checks, and `alpha commit-update` commits its folder whole, lockfile included, as "Set up" commits; for a component at the repository root, alpha's files and the lockfile. Such a component has no baselines and no steps in the compliance plan.

`alpha recipe try` on an adopted recipe whose component has no committed files says to use the kit's recipe instead.

## Consequences

- A repo with docs and no code is adopted in one pass, with the same skeleton and gates as a new project. `/alpha:new-project` still needs an empty folder.
- A repo may mix adopted components and generated ones.
- On no, the component is left out and `/alpha:extend` adds it later. A repo left with no component isn't adopted.
- Not verified: a live `/alpha:adopt` run on a docs-only repo.
