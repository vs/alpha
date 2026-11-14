# 0026. The vulns check scans the lockfiles' folders

Date: 2026-11-14
Status: accepted
Kind: technical

## Context

The vulns check ran `osv-scanner scan source -r .`, which walks the folder and skips what `.gitignore` ignores. It reads the `.gitignore` of an enclosing repository too. A git worktree that Claude Code creates lives in `.claude/worktrees/`, which alpha's `.gitignore` ignores, so in a worktree the walk visited one folder, found nothing and exited 128 with `No package sources found`. The user reported that the check fails this way whenever they work from a worktree. osv-scanner 2.7.1, the newest release, does the same.

Claude made this choice while fixing the bug. Two other options were tried and dropped:

- `-r --no-ignore .` also reads `node_modules`, `.venv` and, from the main checkout, the lockfiles of every other worktree.
- `-L <lockfile>` for each lockfile fails on a lockfile osv-scanner can't read by name. Go's `go.sum` is one; osv-scanner reads `go.mod` instead, and `go.mod` can't be listed as a lockfile because the hooks stop Claude from editing lockfiles.

## Decision

The vulns check runs `osv-scanner scan source --no-ignore <folder>...` on the folder of each lockfile the components' recipes list, without `-r`. It reads the lockfiles and manifests directly in those folders and nothing below them.

## Consequences

- The check gives the same result in a worktree and in the main checkout.
- A lockfile or manifest in a deeper folder that holds no listed lockfile, such as `requirements/dev.txt`, is no longer read. List it in the recipe's `lockfiles` to scan its folder.
- A gitignored manifest that sits directly in a lockfile's folder is now read.
- `osv-scanner.toml` next to a lockfile still applies.
- A project gets the new command from `alpha update` after the next kit release, this repository's own `mise.toml` included.
