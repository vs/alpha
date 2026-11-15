---
name: purge
description: Remove alpha from a project altogether - uninstall its hooks, delete its files, docs, agents and skills, take out what points at them from the files kept, and commit the removal as one commit. Run only when the user asks, as /alpha:purge [folder].
disable-model-invocation: true
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Purge

Remove alpha from a project in one commit. The components' scaffolding (manifests, configs, tests, CI) stays, so the project still builds and tests; git history keeps everything purge deletes.

Folder argument: `$ARGUMENTS`

1. `<target>` is the folder given above, else the current working directory.
2. Tell the user what goes: `.claude/alpha/`, `docs/alpha/` (the specification, principles, dependency log, glossary, adoption plan and feature folders, edited or not), alpha's agents and skills, alpha's entries in `.claude/settings.json`, and the lines and tasks in kept files that point at them; the repository checks that ran alpha's scripts go too, and in an adopted repo the baselined checks report their legacy findings again. Ask: "Remove alpha from <target> in one commit?" and wait for a clear yes.
3. Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" purge <target> --trailer "<line>"` with one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits. Never invent co-author lines.
4. If it refuses, show its message: a file with uncommitted changes it would touch (commit or stash them first), or a kept file it can't clean (the file and line to fix by hand). Then run it again.
5. Report the commit it printed and its notes: the checks gone, and the checks that now report legacy findings.
