---
name: new-project
description: Start a new project with alpha - interview the user area by area, then generate, bootstrap and commit an enforced skeleton in an empty folder. Resumes an interview in progress. Run as /alpha:new-project [folder].
disable-model-invocation: true
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# New project

Take an empty folder to a committed, enforced project skeleton: interview the user about every area, show a summary, then generate the files, install the toolchains and commit. The skeleton holds no app code: only config, docs, test wiring and enforcement.

Folder argument: `$ARGUMENTS`

## 1. Resolve the target folder

1. If a folder was given above, use it (expand `~`, resolve to an absolute path, and create it if it doesn't exist). If nothing was given, use the current working directory. Call it `<target>` from here on.
2. If `<target>/.claude/alpha/project.json` has a `manifest` key, the project is already generated. Tell the user that extending a generated project arrives in a later version of alpha, and stop.
3. List everything in `<target>`, including hidden entries and the contents of `.claude/`. It counts as empty when it holds nothing but `.DS_Store` files, `.claude/alpha/project.json` and `.claude/settings.local.json`.
4. If anything else is there, stop and tell the user: "`<target>` isn't empty (found: <entries>). alpha v0.1 starts projects only in empty folders. Run `/alpha:new-project <new folder>` with a new folder, or move these files out and run it again."

## 2. Start or resume

Save answers only with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '<object>'` (one line; each top-level key sent replaces that key in project.json), never by editing the file. If Claude Code asks to allow it, tell the user that choosing "don't ask again" covers every later save.

- If `<target>/.claude/alpha/project.json` exists, resume: report which areas are done and which are pending (from its `areas`), then continue with the first area that isn't done.
- Otherwise create it:
  `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"schema": 1, "areas": {"identity": "pending", "components": "pending", "git": "pending", "agent_workflow": "pending"}, "overrides": [], "decisions": []}'`

## 3. Load the kit defaults

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults show --json` and keep the result: every recommendation in the interview comes from its `defaults`. Tell the user where they come from, using `source`:
- `live` is true: "Using your kit defaults from <path>. If you override a default during the interview, I'll ask whether to make it your new default; it's saved there only after you say yes."
- `live` is false: "Using the defaults bundled with the installed kit (<reason>). New defaults can't be saved on this machine; any you ask for are noted in this project's decision log instead."

If the command fails, show the user its message. Continue with the bundled defaults only if the message says so; otherwise stop, and tell the user to fix what it names and run `/alpha:new-project <target>` again.

## 4. Interview, area by area

Run the areas in this order, one at a time, never skipping one and never shortcutting one to save time:

1. Identity: `alpha:identity`
2. Components and stacks: `alpha:components`
3. Git history: `alpha:git-history`
4. Agent workflow: `alpha:agent-workflow`

For each area that isn't done, invoke its skill with the Skill tool and follow it through its check, with `<target>` as its target folder. Move on only after the area's check prints `ok`.

Before each area, tell the user in one line which area comes next and what it settles. If the user wants to stop partway, leave project.json as it is and tell them that running `/alpha:new-project <target>` again picks up where they left off.

## 5. Summary and confirmation

Show a summary of every answer in plain words, grouped by area: identity (with each requirement and its acceptance check), components (kind, stack, path, traits; layout; whether they talk), git history, agent workflow, and any overrides and defaults wishes. Ask: "Generate the project with these answers?" and wait.

If the user wants a change, save it with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target>` (with the grilling skill's override protocol where a default changes), re-run that area's check, and show the summary again. Continue only on a clear yes.

## 6. Generate, bootstrap, commit

Run these in order. If one fails, show the user its message (it says what went wrong and how to fix it), fix the cause with them, and rerun that step before going on.

1. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json` must print `ok`.
2. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" generate <target>` writes the skeleton.
3. Tell the user the next step installs each component's toolchain and runs its tests, and can take a minute. Then run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" bootstrap <target>`.
4. Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" commit-skeleton <target> --trailer "<line>"` with one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits, in that order. If there are none, pass no `--trailer`. Never invent co-author lines.

## 7. Final report

Tell the user, briefly:

- **Commits:** the list `commit-skeleton` printed (short hash and subject).
- **Enforced now:**
  - Every commit, by anyone, must follow the convention and scopes (the git `commit-msg` hook).
  - Claude can't skip git hooks, force-push, or amend commits that were already pushed.
  - Claude can't edit protected files (secrets, lockfiles), and must ask the user before skipping a test, adding an ignore comment or loosening strictness.
  - Every file Claude edits is formatted and linted right away.
  - Claude can't finish while it has added a secret, changed source without changing tests, added a dependency without a recorded reason, or left the type checks or tests failing.
  - Each session starts with a warning if the project setup is broken.
- **Not covered yet:** the remaining areas (architecture, errors, testing, UI/UX, documentation, build/CI/hosting, security, dependencies, observability, versioning, data, accessibility, performance) and the principles reviewer arrive in the next version of alpha. Their principles are already in `docs/principles.toml` at the kit defaults.
- **Next:** open `<target>` in Claude Code so the project's own hooks and settings load, and start building.
