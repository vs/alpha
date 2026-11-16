# Install: a new project

Take an empty folder to a committed, enforced project skeleton: interview the user about the install areas, show a summary, then generate the files, install the toolchains and commit. The rules of `SKILL.md` beside this file hold throughout.

## 1. Start or resume

- If `<target>/.claude/alpha/project.json` exists, resume: report which areas are done, which are pending and which are open (from its `areas`), and continue with the first install area in `SKILL.md`'s order that isn't done.
- Otherwise create it:
  `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"schema": 1, "areas": {"identity": "pending", "components": "pending", "testing": "pending", "documentation": "pending", "build": "pending", "security": "pending", "dependencies": "pending", "releases": "pending", "git": "pending", "agent_workflow": "pending", "requirements": "open", "architecture": "open", "errors": "open", "design_language": "open", "ui": "open", "accessibility": "open", "observability": "open", "data": "open", "performance": "open", "auth": "open"}, "overrides": []}'`

## 2. Load the kit defaults

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults show --json` and keep the result: every recommendation in the interview comes from its `defaults`. Tell the user where they come from, using `source`:

- `checkout` is false: "Using the defaults of the installed alpha plugin."
- `checkout` is true: "Using the defaults of the alpha checkout at <path> (ALPHA_SOURCE)."
- When `user_defaults` is a path, add: "Your own defaults from <user_defaults> apply on top."

Then: "If you override a default during the interview, I'll ask whether to make it your default for future projects; it's saved with your own defaults only after you say yes."

## 3. Interview, area by area

Run the install areas in `SKILL.md`'s order, one at a time, never skipping one and never shortcutting one to save time. For each that isn't done, read its guide and follow it through its check, with `<target>` as its target folder; move on only after the check prints `ok`. Before each area, tell the user in one line which comes next and what it settles. If the user wants to stop partway, leave project.json as it is and tell them `/alpha:install <target>` picks up where they left off.

## 4. Summary and confirmation

Show a summary of every answer in plain words, grouped by area: identity (name, value proposition, license), components (kind, stack, path, traits; layout; whether they talk), testing (levels per component), documentation (where user docs live; each mapping), build (CI, environments, each component's artifact and hosting), security (secret store, extra protected paths), dependencies (updates and schedule), releases (scheme, changelog, scope, process), git history, agent workflow, and any overrides and defaults wishes. Then list the open product areas in one line, saying `/alpha:specify` settles each. Ask: "Generate the project with these answers?" and wait.

If the user wants a change, save it with `answers write` (with the grilling skill's override protocol where a default changes), re-run that area's check, and show the summary again. Continue only on a clear yes.

## 5. Generate, bootstrap, commit

In order:

1. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json` must print `ok`.
2. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" apply <target>` writes the skeleton (and runs `git init` on a plain folder).
3. Tell the user the next step installs each component's toolchain and runs its tests, then installs the repository checks' tools with mise and runs them, and can take a few minutes. Then run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" bootstrap <target>`.
4. Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" commit <target> --trailer "<line>"` with one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits, in that order. If there are none, pass no `--trailer`. Never invent co-author lines.
5. For each recipe drafted in this interview (the `recipes` in project.json), ask: "Save the <stack> recipe for your future projects?" On yes, run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe save <target> <stack>`. Exit 0: tell the user it's saved with their own recipes (the path it prints). Exit 3: show the message and follow its fix.

## 6. Final report

Tell the user, briefly:

- **Commits:** the list `commit` printed (short hash and subject).
- **Enforced now:**
  - Every commit, by anyone, must follow the convention and scopes (the git `commit-msg` hook).
  - Claude can't skip git hooks, push with a plain `--force`, or rewrite main; it may rebase its own branch and push it with `--force-with-lease`.
  - Claude can't edit protected files (secrets, lockfiles, and any extra protected paths), and can't skip a test, add an ignore comment or loosen strictness until a row in CONTRIBUTING.md's Exceptions table names the file and says why.
  - Every file Claude edits is formatted and linted right away.
  - Claude can't finish a turn while it has added a secret, changed source without changing tests (or saying why a trivial change needs none), changed a mapped path without its docs, added a dependency without a recorded reason, or left the type check or structure check failing.
  - Before its work reaches main (a push to main or a pull request merge), each changed component's full test suite must pass, and the principles reviewer must have reviewed the branch with no open findings. The review runs once there, on what changed since the last one; Claude may accept a finding it disproves with an `Accepts:` trailer, but a finding on a risk path needs your "accept".
  - CI runs every component's checks on each push to main and each pull request (when CI was chosen); the workflow runs once the repository is on GitHub. Dependabot opens update pull requests on the chosen schedule (when chosen).
  - Only `/alpha:uninstall` switches these hooks off; `/alpha:install` switches them back on.
  - Each session starts with a warning if the project setup is broken.
- **Reports on request:** `/review-change` (a change) and `/audit` (the whole repo); each changes no code.
- **Drafted recipes:** name each stack whose recipe was drafted in this interview, say it's less proven than the kit's own, and whether it was saved.
- **Not settled yet:** the open product areas, each with the `/alpha:specify` request that settles it (`docs/alpha/specification.md` lists them); their principles stay off until then.
- **Next:** open `<target>` in Claude Code so the project's own hooks and settings load, and start building with `/alpha:do <task>`.
