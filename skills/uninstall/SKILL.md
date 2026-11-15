---
name: uninstall
description: Switch alpha's hooks off in a project - its Claude Code hook entries and its git commit-msg hook - deleting no file and committing nothing. Run only when the user asks, as /alpha:uninstall [folder].
disable-model-invocation: true
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Uninstall

Switch alpha's hooks off. This is the one sanctioned way to do it: the guards block every other. It deletes no file and commits nothing, so `/alpha:install` switches the hooks back on exactly as they were.

Folder argument: `$ARGUMENTS`

1. `<target>` is the folder given above, else the current working directory.
2. Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" uninstall <target>`.
3. Tell the user what it printed: alpha's hook entries taken out of `.claude/settings.json`, and `core.hooksPath` unset, or in a repo whose own hook manager runs git's hooks, alpha's marked call taken out of that manager's commit-msg file. A line it says to remove by hand is the user's to remove.
4. Say that the hooks stop in sessions started from now on (this one loaded them already), that `/alpha:install` switches them back on, and that `/alpha:purge` removes alpha's files too.
