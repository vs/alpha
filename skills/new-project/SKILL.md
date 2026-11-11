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
2. If `<target>/.claude/alpha/project.json` has a `manifest` key, the project is already generated. Tell the user, then invoke `alpha:extend` with the Skill tool to change it, passing `<target>` as its arguments.
3. List everything in `<target>`, including hidden entries and the contents of `.claude/`. It counts as empty when it holds nothing but `.DS_Store` files, `.claude/alpha/project.json` and `.claude/settings.local.json`.
4. If anything else is there, stop and tell the user: "`<target>` isn't empty (found: <entries>). alpha v0.1 starts projects only in empty folders. Run `/alpha:new-project <new folder>` with a new folder, or move these files out and run it again."

## 2. Start or resume

Save answers only with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '<object>'` (one line; each top-level key sent replaces that key in project.json), never by editing the file. Type the JSON straight into that one command: never build it with python3, a heredoc, a script or a temporary file, which Claude Code would ask about on every save. If Claude Code asks to allow it, tell the user that choosing "don't ask again" covers every later save.

- If `<target>/.claude/alpha/project.json` exists, resume: report which areas are done and which are pending (from its `areas`; an area missing from `areas`, because the interview started on an older alpha, is pending), then continue with the first area in the order below that isn't done.
- Otherwise create it:
  `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"schema": 1, "areas": {"identity": "pending", "components": "pending", "architecture": "pending", "errors": "pending", "testing": "pending", "ui": "pending", "documentation": "pending", "build": "pending", "security": "pending", "dependencies": "pending", "observability": "pending", "releases": "pending", "data": "pending", "accessibility": "pending", "performance": "pending", "git": "pending", "agent_workflow": "pending"}, "overrides": [], "decisions": []}'`

## 3. Load the kit defaults

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults show --json` and keep the result: every recommendation in the interview comes from its `defaults`. Tell the user where they come from, using `source`:

- `checkout` is false: "Using the defaults of the installed alpha plugin."
- `checkout` is true: "Using the defaults of the alpha checkout at <path> (ALPHA_SOURCE)."
- When `user_defaults` is a path, add: "Your own defaults from <user_defaults> apply on top."

Then: "If you override a default during the interview, I'll ask whether to make it your default for future projects; it's saved with your own defaults only after you say yes."

If the command fails, show the user its message, then stop, and tell the user to fix what it names and run `/alpha:new-project <target>` again.

## 4. Interview, area by area

Run the areas in this order, one at a time, never skipping one and never shortcutting one to save time:

1. Identity: `alpha:identity`
2. Components and stacks: `alpha:components`
3. Architecture: `alpha:architecture`
4. Errors: `alpha:errors`
5. Testing: `alpha:testing`
6. UI: `alpha:ui`
7. Documentation: `alpha:documentation`
8. Build, CI and hosting: `alpha:build-and-hosting`
9. Security and secrets: `alpha:security`
10. Dependencies: `alpha:dependencies`
11. Observability: `alpha:observability`
12. Versioning and releases: `alpha:releases`
13. Data and migrations: `alpha:data`
14. Accessibility: `alpha:accessibility`
15. Performance: `alpha:performance`
16. Git history: `alpha:git-history`
17. Agent workflow: `alpha:agent-workflow`

For each area that isn't done, invoke its skill with the Skill tool and follow it through its check, with `<target>` as its target folder. Move on only after the area's check prints `ok`.

Before each area, tell the user in one line which area comes next and what it settles. If the user wants to stop partway, leave project.json as it is and tell them that running `/alpha:new-project <target>` again picks up where they left off.

## 5. Summary and confirmation

Show a summary of every answer in plain words, grouped by area: identity (with each requirement and its acceptance check), components (kind, stack, path, traits; layout; whether they talk), architecture (responsibilities, calls, contract, glossary), errors (format per component; categories), testing (levels per component), UI (per UI component: library, tokens, theming, visual regression; or no UI), documentation (where user docs live; each mapping), build (CI, environments, each component's artifact and hosting), security (secret store, auth, extra protected paths), dependencies (updates and schedule), observability (per deployed component, or not applicable), releases (scheme, changelog, scope, process), data (per component that stores data: storage and migrations; ML data versioning, seeds and tracking; or nothing stored), accessibility (level and checks per UI component, or no UI), performance (budgets per component, or none), git history, agent workflow, and any overrides and defaults wishes. Ask: "Generate the project with these answers?" and wait.

If the user wants a change, save it with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '<object>'` on one line (with the grilling skill's override protocol where a default changes), re-run that area's check, and show the summary again. Continue only on a clear yes.

## 6. Generate, bootstrap, commit

Run these in order. If one fails, show the user its message (it says what went wrong and how to fix it), fix the cause with them, and rerun that step before going on.

1. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json` must print `ok`.
2. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" generate <target>` writes the skeleton.
3. Tell the user the next step installs each component's toolchain and runs its tests, then installs the repository checks' tools with mise and runs them, and can take a few minutes. Then run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" bootstrap <target>`.
4. Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" commit-skeleton <target> --trailer "<line>"` with one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits, in that order. If there are none, pass no `--trailer`. Never invent co-author lines.
5. For each recipe drafted in this interview (the `recipes` in project.json), ask: "Save the <stack> recipe for your future projects?" On yes, run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe save <target> <stack>`. Exit 0: tell the user it's saved with their own recipes (the path it prints) and the next project can use it. Exit 3: show the message and follow its fix.

## 7. Final report

Tell the user, briefly:

- **Commits:** the list `commit-skeleton` printed (short hash and subject).
- **Enforced now:**
  - Every commit, by anyone, must follow the convention and scopes (the git `commit-msg` hook).
  - Claude can't skip git hooks, push with a plain `--force`, or rewrite main; it may rebase its own branch and push it with `--force-with-lease`.
  - Claude can't edit protected files (secrets, lockfiles, and any extra protected paths), and can't skip a test, add an ignore comment or loosen strictness until a decision record names the file and says why.
  - Every file Claude edits is formatted and linted right away.
  - Claude can't finish while it has added a secret, changed source without changing tests (or saying why a trivial change needs none), changed a mapped path without its docs, added a dependency without a recorded reason, or left the type checks or tests failing.
  - Claude can't edit a migration that existed before the session: migrations are append-only, so a fix is a new migration (when a component stores data).
  - CI runs every component's checks on each push to main and each pull request (when the user chose CI). Tell the user the workflow runs once they push the repository to GitHub.
  - Dependabot opens update pull requests on the chosen schedule (when chosen), also once the repository is on GitHub.
  - Claude can't push to main or merge a pull request with unreviewed changes or open review findings, and can't finish with open findings (in batched mode, also not with unreviewed changes past the thresholds). Claude may accept a finding it disproves, recorded in the decision log; a finding on a risk path needs your "accept".
  - Each session starts with a warning if the project setup is broken.
  - Every `shortcut:` comment names when to upgrade it (the `shortcuts` repository check).
- **Reports on request:** `/review-change` (a change), `/audit` (the whole repo) and `/debt` (the deliberate shortcuts); each changes no code.
- **Drafted recipes:** name each stack whose recipe was drafted in this interview, say it's less proven than the kit's own, and whether it was saved to the kit.
- **Next:** open `<target>` in Claude Code so the project's own hooks and settings load, and start building.
