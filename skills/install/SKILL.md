---
name: install
description: Put alpha into a folder - a new project in an empty folder, an adoption on a branch in an existing repo, or alpha's hooks back on where they were switched off; in an adopted repo, carry out the compliance plan's next step. Resumes an interview in progress. Run as /alpha:install [folder].
disable-model-invocation: true
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Install

Put alpha's development process into a folder: config, docs, test wiring and enforcement, never app code. What it does depends on the folder's state, which alpha's CLI tells apart.

Folder argument: `$ARGUMENTS`

## 1. Target and state

`<target>` is the folder given above (expand `~`, resolve it to an absolute path, create it if it doesn't exist), else the current working directory. Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" status <target>`. It prints the state's name, and for some a colon and a detail. Take the path for that state:

| State | Path |
|---|---|
| `empty` | A new project: read `${CLAUDE_PLUGIN_ROOT}/skills/install/new-project.md` and follow it. |
| `interview` | An interview is under way. With an `adoption` key in `<target>/.claude/alpha/project.json`, follow `adopt.md` beside this file; otherwise `new-project.md`. Each resumes at the first step not done. |
| `existing` | An existing repo: read `${CLAUDE_PLUGIN_ROOT}/skills/install/adopt.md` and follow it. |
| `hooks-off` | alpha is installed with its hooks switched off. Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" hooks on <target>` without asking, and tell the user what it printed: what it switched back on. It commits nothing. |
| `installed` | alpha is installed with its hooks on. When the detail names the adoption plan's next step, carry it out as `adopt.md`'s "The plan" says. Otherwise tell the user it's installed, and that `/alpha:extend` changes a component or a setup answer, `/alpha:specify` settles a product area, and `/alpha:update` brings it to a newer alpha. |
| `adopting` | Show the detail: the branch `alpha/adopt` exists, so switch to it and run `/alpha:install` again. Stop. |
| `uncommitted`, `not-a-repo`, `missing` | Show the detail, which says what to do first (commit, stash, switch to a branch, `git init`, create the folder), and stop. |
| `old-kit` | An alpha before 1.0 set it up. Show the detail and point to the by-hand steps in the "Projects an older alpha set up" section of alpha's README; don't change anything. Stop. |

## Rules for every path

- Ask one question at a time, as the `alpha:grilling` skill's "Rounds" says: a choice, a yes or no or a confirmation in the `AskUserQuestion` dialog when that tool is in your tool list, a draft for the user to edit in plain text.
- Save answers only with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '<object>'`: one line, the JSON typed straight into the command, never a heredoc, a python3 script or a temporary file (Claude Code would ask on every save). Each top-level key sent replaces that key in project.json. If Claude Code asks to allow it, tell the user that "don't ask again" covers every later save.
- The interview covers only the install areas, in this order, each from its guide in `${CLAUDE_PLUGIN_ROOT}/skills/install/areas/`: `identity.md`, `components.md`, `testing.md`, `documentation.md`, `build.md`, `security.md`, `dependencies.md`, `releases.md`, `git.md`, `agent_workflow.md`. Read each guide with the Read tool and follow it through its check. The product areas (requirements, architecture, errors, design language, UI, accessibility, observability, data, performance, auth) stay open: never settle one here. When the user wants one settled, say `/alpha:specify <area>` does it once install is done.
- What the project is about may be asked in one line, for the value proposition; nothing more of the product.
- When a CLI step fails, show its message (it says what went wrong and how to fix it), fix the cause with the user, and rerun that step before going on.
