# 0022. alpha update upgrades older kit projects

Date: 2026-11-13
Status: accepted
Kind: product

## Context

The spec kept existing projects as they were when the kit changed: §11 says "Existing projects never change when kit defaults change", and §8a D4 has `alpha update` render before and after with the current kit, so kit changes cancel out. Its §15 left "Re-syncing a project with newer kit defaults" for later. alpha's own repo then showed the cost: adopted with kit 0.4.2, it kept running its 0.4.2 hooks and checks after 0.4.3 shipped, without the commit-hook bypass fixes or the secrets check that skips gitignored files. No supported command could bring them in, and copying them by hand would edit generated files.

Asked what was left to make alpha compatible with itself, Claude recommended building the upgrade into `alpha update`. The user answered: "Yes, implement all of them, don't ask me anything, choose those options you'd recommend me". The merge rules below are Claude's choices under that answer.

## Decision

When the manifest's `kit_version` is older than the running alpha, `alpha update` also upgrades the project to this kit:

- The kit that set the project up renders what it wrote: its own code renders the answers it was set up from, and lists the files it copies (hooks, checks, skills, agents, the git hook). Each file then merges three ways, as in any update: that render, the user's copy, and this kit's. The kit's changes come through as alpha's; the user's edits stay, and where both changed the same lines alpha leaves a proposal to merge by hand. A file the repo had before adoption merges the same way, since the render holds only alpha's part of it.
- alpha finds that kit in the folder the manifest names, at the commit it recorded for a checkout, in the plugin cache's folder for that version, or at this checkout's `v<version>` tag. Without it, the update stops and says where to put it.
- A project set up by a newer alpha than the running one is refused, with the fix: update alpha.

The dry run names the upgrade (`alpha update (kit 0.4.2 to 0.4.3): …`), so it still happens only when the user runs the update. Claude first tried the digest the manifest records as the base, but that digest is taken from disk after each update, so it holds the user's earlier edits and the merge would have dropped them; the old kit's own render has none.

## Consequences

Existing projects, generated or adopted, gain each kit's fixes and gates through `alpha update`, then `alpha commit-update`. Any update of an older kit project, such as one `/alpha:extend` makes to add a component, carries the whole kit upgrade with it, so its dry run lists more files than the requested change needs. Spec §11, §8a D4, §5b and §15 change to match. The "may include kit changes" notes and the "left out" newer-kit files go away. The kit's version must be bumped with every release that changes what it writes, because the upgrade starts only from an older version.
