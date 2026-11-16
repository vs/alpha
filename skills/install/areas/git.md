# Git history

## Before you start

`/alpha:install` reads this guide for a new project's or an adoption's interview, and `/alpha:extend` when a change revisits this area. `<target>` is their target folder; the answers live in `<target>/.claude/alpha/project.json`. Their rules win over this guide's where they differ. When the user asks to revisit this area outside them, run `/alpha:extend` with the request.

## Purpose

Decide how the project's history reads: the commit message convention, the scopes a commit may name, and how work reaches the main branch. A git `commit-msg` hook enforces the convention and scopes for everyone who commits, so a clean, readable history is checked, not hoped for.

## Fields this area settles

- `git.convention` - `"conventional"` (the only convention alpha enforces).
- `git.scopes` - the scopes a commit may name, e.g. `["api", "web"]`.
- `git.branching` - `"trunk"` or `"feature-branches"`.
- `areas.git` - `"in_progress"` while you work, `"done"` at the end.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as a design tree in rounds. All three are independent, so ask them in one round.

- **Convention** - recommend `defaults.git.convention`. Explain in plain words: every commit reads `type(scope): description`, e.g. `feat(api): add image upload`; the description is at most 50 characters, imperative, and has no trailing period, and may start lowercase; body lines wrap at 72. The allowed types are `defaults.git.types`. Say plainly that alpha enforces conventional commits only; if the user wants another convention, explain it can't be enforced yet and ask them to accept conventional or stop here.
- **Scopes** - recommend the component names from `components[].name` (the kit's default). Explain: a scope says which part a commit touches. The list is what the docs suggest; the hook accepts any scope of lowercase letters, digits and hyphens (`[a-z0-9-]+`), so a commit can also name an area such as `deps`, or leave the scope out. The user may add extra scopes to the list; each must use that same form.
- **Branching** - recommend `defaults.git.branching`. Explain the two choices in one line each: `trunk` (small commits straight to the main branch, each leaving the checks green) and `feature-branches` (short-lived branches merged through pull requests; before a pull request, Claude rebases the branch on main into small, ordered commits and pushes it with `--force-with-lease`; the hooks block a plain `--force` and any rewrite of main).

When an answer differs from a default, follow the grilling skill's override protocol (keys `git.convention`, `git.branching`; scopes differ per project, so a changed scope list doesn't go through the protocol).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "git": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `git` set to `"in_progress"`.
3. When the user confirms the area, save the `git` object `{"convention", "scopes", "branching"}`. Keep the exact field names.
4. In the same call, save `areas` with `git` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area git`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
