---
name: git-history
description: Settle a new project's git history rules in the alpha interview - commit convention, commit scopes and branching model. Use only inside an alpha project interview (/alpha:new-project) or alpha:extend or when the user asks to revisit the git history rules of a project alpha is setting up.
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Git history

## Before you start

`<target>` is the folder `/alpha:new-project` is working in; when the user calls this skill directly, it's the current working directory. The answers live in `<target>/.claude/alpha/project.json`. Check it first:

- No project.json: tell the user to start with `/alpha:new-project`, which runs every area in order, and stop.
- project.json has a `manifest` key: the project is already generated. If the `alpha:extend` skill sent you here, go on as it says. Otherwise invoke `alpha:extend` with the Skill tool and follow it; it brings you back here.
- `areas.performance` isn't `"done"`: tell the user the earlier areas come first and to run `/alpha:new-project`, and stop.
- Otherwise go on. When the user called this skill directly, use the current answers as the recommendations, and when you finish, tell them to run `/alpha:new-project` to continue.

## Purpose

Decide how the project's history reads: the commit message convention, the scopes a commit may name, and how work reaches the main branch. A git `commit-msg` hook enforces the convention and scopes for everyone who commits, so a clean, readable history is checked, not hoped for.

## Fields this area settles

- `git.convention` - `"conventional"` (the only convention alpha v0.1 enforces).
- `git.scopes` - the scopes a commit may name, e.g. `["api", "web"]`.
- `git.branching` - `"trunk"` or `"feature-branches"`.
- `areas.git` - `"in_progress"` while you work, `"done"` at the end.
- `decisions[]` - one entry with `"area": "git"`.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds. All three are independent, so ask them in one round.

- **Convention** - recommend `defaults.git.convention`. Explain in plain words: every commit reads `type(scope): description`, e.g. `feat(api): add image upload`; the description is at most 50 characters, imperative, and has no trailing period, and may start lowercase; body lines wrap at 72. The allowed types are `defaults.git.types`. Say plainly that v0.1 enforces conventional commits only; if the user wants another convention, explain it can't be enforced yet and ask them to accept conventional or stop here.
- **Scopes** - recommend the component names from `components[].name` (the kit's default). Explain: a scope says which part a commit touches, and the hook rejects scopes not on this list; a commit may also leave the scope out. The user may add extra scopes (e.g. `deps`). Every scope must use only lowercase letters, digits and hyphens (`[a-z0-9-]+`), or no commit could ever name it.
- **Branching** - recommend `defaults.git.branching`. Explain the two choices in one line each: `trunk` (small commits straight to the main branch, each leaving the checks green) and `feature-branches` (short-lived branches merged through pull requests; before a pull request, Claude rebases the branch on main into small, ordered commits and pushes it with `--force-with-lease`; the hooks block a plain `--force` and any rewrite of main).

When an answer differs from a default, follow the grilling skill's override protocol (keys `git.convention`, `git.branching`; scopes differ per project, so a changed scope list is recorded in the decision without asking).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "git": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` and `decisions` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `git` set to `"in_progress"`.
3. When the user confirms the area, save the `git` object `{"convention", "scopes", "branching"}`. Keep the exact field names.
4. In the same call, save `decisions` with one entry for this area, replacing any earlier one with `"area": "git"`:
   `{"area": "git", "title": "…", "context": "…", "decision": "…", "consequences": "…"}`. `title` names the choice (e.g. "Conventional commits on trunk"); `context` is who commits and why the history matters; `decision` names the convention, scopes and branching; `consequences` says what the hook will reject, plus any defaults wish from the override protocol.
5. In the same call, save `areas` with `git` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area git`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
