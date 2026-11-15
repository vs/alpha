# Prompt: rewrite alpha

Run this on `main` after `feat/no-decision-records` is merged. Create a worktree and work from there.

---

You are rewriting alpha, a Claude Code plugin that sets up a project's development process: config, checks, hooks, a reviewer and process docs. Treat this as a new product built to the requirements below: the code, skills, hooks, docs and tests are all rewritten. The current implementation is a source of knowledge (what works, which tools and commands each stack needs, which edge cases bit), not a structure to keep. Read `CLAUDE.md`, `README.md`, `CONTRIBUTING.md`, `docs/specification.md` and the code before you plan.

The requirements are the user's, settled with them. Don't add capabilities or behaviors they didn't ask for. When something they don't settle comes up, ask them, one question at a time.

## Stack

alpha stays a Python CLI (`bin/alpha`, Python 3.11+, uv) plus Claude Code plugin skills. The hooks and checks copied into projects stay plain Python with no dependencies.

## Commands

Commands that need Claude are plugin skills only. Commands that don't also work from the terminal as `bin/alpha <command>`.

| Command | Form |
|---|---|
| `install` | skill (`/alpha:install`) |
| `extend` | skill |
| `specify` | skill |
| `do` | skill |
| `uninstall` | skill and CLI |
| `purge` | skill and CLI |
| `update` | skill and CLI: the CLI merges, the skill resolves conflicts |

The other CLI subcommands (`answers`, `recipe`, `registry`, `defaults`, `baseline`, `adopt`, `generate`, `bootstrap`, the commit steps) remain as helpers the skills call. Rename or merge them as the new design needs.

## Requirements

### Entry points

1. **`install`** is the single way to put alpha into a folder.
   - An empty folder: it does what `new-project` does today, limited to the scope in requirement 5.
   - A folder with source code: it runs today's adoption: survey, interview recommending what the repo already uses, install on the `alpha/adopt` branch with the repo's own files merged, baselines of legacy findings, compliance plan. Its interview has the same scope as requirement 5, and the compliance plan moves to `docs/alpha/`. Nothing else in adoption changes in this rewrite.
   - Running `install` where alpha is installed but its hooks are off turns them back on without asking anything.
2. **`uninstall`** removes alpha's hooks:
   - alpha's hook entries in `.claude/settings.json`;
   - git's `core.hooksPath`.

   It deletes no other file and doesn't commit. It must work despite alpha's own guards, which block edits to the hook wiring and changes to `core.hooksPath`. And it is the **only** command that can remove the hooks: the guards keep blocking every other way.
3. **`purge`** runs `uninstall`, then deletes every alpha-specific file and commits the removal as one commit.
   - **Deleted:** `.claude/alpha/` (hooks, checks, state, answers), alpha's agents and skills in `.claude/`, alpha's entries in `.claude/settings.json`, `docs/alpha/`. They go even when the user has edited them.
   - **`CLAUDE.md`:** only the lines that point at alpha's hooks and docs are removed.
   - **Kept:** the scaffolding alpha generated: tool configs, `mise.toml`, CI workflows, `CONTRIBUTING.md`, `README.md`, `LICENSE`, the rest of `CLAUDE.md`. The project still builds and tests without alpha.
4. **`extend`** stays: in a project where alpha is installed, the user describes a change, such as adding a component, and alpha applies it.

### Scope of install

5. `install` sets up the **development process only**: how tests run, type checks, lints, spelling and grammar checks, and everything else around how the project is developed. It may ask briefly what the project is about, and nothing deeper. Today's 18 interview areas split as follows:
   - **`install` sets up:**
     - identity: name, one-line purpose and license only;
     - components, testing, documentation, build-and-hosting, dependencies, releases, git-history, agent-workflow;
     - security: secrets and protected paths only.
   - **Left open for `specify`:**
     - identity: users and requirements;
     - architecture (with the glossary), errors, design-language, ui, accessibility, observability, data, performance;
     - security: authentication.

### Where docs go

6. Docs live in three places:
   - `CONTRIBUTING.md` stays at the root and holds the process: what `install` sets up is described there.
   - Every other doc alpha generates goes under `docs/alpha/`, including the principles (`docs/alpha/principles.toml`) and the dependency log. alpha writes nothing else into `docs/`. When the project already has a doc that covers an area, the file in `docs/alpha/` refers to it instead of repeating it.
   - At the root, alpha also generates `CLAUDE.md` (it must be there for Claude Code), `README.md` (name, purpose, how to set up, test and run) and `LICENSE`, as today. In an existing repo it never overwrites them; it proposes its changes.

### Product layer

7. **`specify`** works on the product layer, and only when the user asks for it: the areas requirement 5 leaves open (specification, UI and UX, design language, technical details and the rest). It can work on one area or several, at any time. An open area it works on gets its docs in `docs/alpha/` and is then closed.

### Doing work

8. **`go` is renamed `do`.** It keeps the playbooks that came from pstack, with feature development as the focus: research, then brainstorming the feature with the user, as superpowers does. Everything about one feature goes in `docs/alpha/features/<date>-<feature>/`: research documents (from a deep research into how other projects build the feature), the feature's specification, and its implementation plan.

### Review

9. **The principles review runs only on merge,** before Claude's work reaches main. It doesn't run at Stop or after a task, and `/alpha:do` runs no extra whole-branch review. A review costs a lot of time and tokens. It must never loop: a change made to answer a review must not start another full review, and so on. Fast checks run as requirement 13 says.
10. **Review results live in git notes attached to trees.**
    - Reviewing a tree adds a note to that **tree** object (not a commit) under its own notes ref, holding the review's result.
    - To find what was last reviewed, walk the history, map each commit to its tree, and look for a tree that has a note. When none has one, the branch's changes since main are reviewed.
    - Compare the last reviewed tree with the current one to get the changed files. Only those files are reviewed.
    - A review's findings are the only thing that blocks after it. A fix is checked against those findings without raising new ones on code already reviewed.
    - The notes stay local and are never pushed. Another clone reviews again, which is accepted.

### Updates

11. **`update` stays and does what it does today:** it merges changed answers into a project, and upgrades a project an older kit set up. Reconsider whether it's still needed once the rest is designed. If you think it should change or go, ask the user.

### What stays from today

12. These capabilities stay, rebuilt to fit the requirements above:
    - **Setup data:**
      - stack recipes for Python, TypeScript and Rust;
      - drafted recipes for other stacks (`stack-recipe`, `recipe try/save`);
      - the tool registry with pinned versions and `registry stale`;
      - the user's defaults layer in `~/.config/alpha/`, with "make this the default for future projects?".
    - **Checks:**
      - repository checks: secrets, vulnerabilities, spelling, Markdown, links, agent config lint, weekly tool freshness;
      - the migration checks (immutable migrations, SQL migration lint) and review dates on security exceptions;
      - the palette check, which belongs to the design language under `specify`;
      - the diff-coverage gate;
      - the full test suite of each changed component before main, remembering a pass.
    - **Adopted repos:** baselines and the ratchet; the compliance plan.
    - **Generated config:**
      - CI generation: GitHub Actions workflows, the scheduled workflow, Dependabot;
      - per-stack permissions in `.claude/settings.json`.
    - **Agents and skills:** the `principles-reviewer` agent, the `committer` agent and `/commit`, `review-change`, `/audit`, the `decision` skill (where a decision goes in the docs).
    - **Hooks:**
      - the command guard, trimmed to a short list;
      - the file guard;
      - the Stop checks;
      - the post-edit checks;
      - session and subagent context;
      - the `commit-msg` git hook;
      - `untested` notes.
13. **Fast checks run where they do today.** Claude Code hooks format, lint and type-check after each edit, and run the type check, structure check and fast repo checks at Stop; these bind Claude only. The only git hook is `commit-msg`, which checks the message format for everyone. No `pre-commit` hook.

### Dropped

14. These go, with their code, tests and docs:
    - the mutation-testing gate;
    - `/debt` and the `shortcut:` ledger check;
    - the interview evals (`bin/alpha-evals`, `evals/`).

### Constraints

15. **No decision log.** Decisions update the current docs (`docs/alpha/`, `CONTRIBUTING.md`); there are no decision records in any form. `feat/no-decision-records` already did this. Build on it.
16. **No file hashes or tree snapshots in committed files.** Today `.claude/alpha/project.json` → `manifest.files` holds `path: sha256:…` for every file alpha wrote, and nothing reads the hashes. That must not exist in the rewrite. Git objects and git notes are fine.

## How to work

1. Read the current code and docs to learn what each piece does and why.
2. Write the rewrite's research, specification and implementation plan in `docs/alpha/features/<date>-alpha-rewrite/` (requirement 8): requirements with an acceptance check and a test for each, the design, and a plan of tasks. The user approves the specification before any code.
3. Build on a branch in your worktree. Each task leaves the project's checks green and is one commit per the commit convention. The tests are rewritten with the code.
4. Rewrite alpha's own docs to match the new product: `README.md`, `CLAUDE.md`, `CONTRIBUTING.md` and `docs/alpha/`.
5. At the end, report what was built per requirement, what you didn't verify live, and what the user must do by hand for projects alpha already set up.
