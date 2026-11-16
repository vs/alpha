# alpha

alpha is a Claude Code plugin that puts a development process into a project: principles, docs, Claude Code and git hooks, CI and test wiring, with no app code. `/alpha:install` sets up a new project in an empty folder, adopts an existing repo on `alpha/adopt` with baselines for its legacy findings and a compliance plan, or switches the hooks back on. What it does: [docs/specification.md](docs/specification.md).

## Dev commands

- `mise install`, then `mise run check`: every check the kit runs on itself (typos, rumdl and agnix on the docs and skills, then pytest, ruff and pyright).
- `uv run pytest`, `uv run ruff check`, `uv run ruff format`, `uv run pyright`.
- `bin/alpha status <folder>`: the folder's state, which `/alpha:install` routes on (empty, interview, existing, adopting, uncommitted, not-a-repo, old-kit, hooks-off, installed).
- `bin/alpha apply <folder> [--dry-run]`, then `bin/alpha bootstrap <folder> [--component …] [--capture-baselines]` and `bin/alpha commit <folder> [--trailer …]`: writes alpha's files from finished answers (`answers check` first; `answers write <target> --json '…'` saves an area). On an empty folder it sets up a new project; on an existing repo it adopts it on `alpha/adopt`, where every file the repo already has becomes a proposal; on an installed project it is `bin/alpha update <project> [--dry-run]`. Changes merge three ways against the render alpha last committed, kept in git (commits under `refs/alpha/rendered`, named by notes under `refs/notes/alpha-rendered`), never in project.json; alpha's own files (hooks, checks, the git hook, the copied agents and skills) are always replaced.
- `bin/alpha uninstall <project>` and `bin/alpha hooks on <project>`: switch alpha's hooks off and back on, deleting no file and committing nothing. Off takes alpha's entries out of `.claude/settings.json` and unsets `core.hooksPath`, or in chain mode moves the call between `# alpha:begin` and `# alpha:end` out of the hook manager's commit-msg file into `.claude/alpha/state/chain.json`; on restores the hooks table as it was when nothing changed since, else merges alpha's entries back.
- `bin/alpha purge <project> [--trailer …]`: alpha out of a project in one commit (`chore: Remove alpha`). It plans everything in memory, refuses while a file it would touch has uncommitted changes, uninstalls, deletes `.claude/alpha/`, `docs/alpha/` and alpha's agents and skills (never a path in `installed.preexisting`), removes only what points at them from the kept files alpha wrote, maps ratcheted commands back to plain ones, and drops alpha's refs and notes. A kept file it can't clean stops it before anything is written.
- `bin/alpha recipe list|check|try|save`, `bin/alpha registry list|show|stale` and `bin/alpha defaults show|set`: the kit's stacks and drafted recipes (a drafted recipe's proof lives in `.claude/alpha/state/proofs.json`), the reviewed tool registry (`stale` names tools not reviewed in 180 days) and the merged defaults.
- `bin/alpha adopt survey <repo> [--save]`: what an existing repo already has, in facts: candidate components from the recipes' `[detect]` markers, the files `defaults/survey.toml` names, branch, clean tree and commit convention. An adopted recipe (`"adopted": true`, optionally `"extends": "<kit stack>"`) runs the repo's own tools; `alpha recipe try` proves it on a throwaway worktree of the repo's HEAD, where a failing check passes only if its baseline reader reads its findings. A kit recipe's `[adopt]` table holds the command variants an adopted recipe uses, so a root component's tools skip `.claude/`. `adoption.git_hooks` is `alpha` (alpha sets `core.hooksPath`) or `chain` (the repo's hook manager calls alpha's commit-msg check).
- `bin/alpha adopt gaps|next|start|done|drop <repo>`: the compliance plan of an adopted repo, kept in `adoption.steps` and rendered as `docs/alpha/adoption.md`. `gaps [--save]` adds the mechanical steps; `next` names the next ready step; `done` marks a step only when every condition of its acceptance holds (`run`, `recipe`, `no_baseline`, `commit_hook`, `confirm` with `--confirmed-by-user`); `drop --reason '…'` needs the reason the user agreed to.
- `bin/alpha baseline show|capture|tighten <project>`: the per-file, per-rule baselines of legacy findings. Only a project whose answers list `adoption.baselines` has any. The patterns that read each tool's findings are matched against real output in `tests/fixtures/baseline-output/`; re-record those when a pinned tool's version changes.
- The review: `python3 .claude/alpha/hooks/review.py brief` in a project prints what the principles reviewer reviews; `review_record.py` writes its report as a note on the reviewed tree under `refs/notes/alpha-review`, which stays local. The merge guard in `guard_bash.py` asks for it before a push to main or a pull request merge.

## Rules

- Commits use conventional commits with the scopes `git.scopes` lists (alpha, hooks, recipes, defaults, spec). The description after the `type(scope):` prefix is at most 50 chars, imperative, capitalized, no trailing period. Body lines wrap at 72.

## Install and verify

Try alpha without installing it: start Claude Code with the plugin loaded for that session only, then install it into a new folder.

```sh
claude --plugin-dir ~/workspace/alpha
/alpha:install ~/code/my-new-project
```

`/alpha:install ~/code/that-repo` adopts an existing repo (clean tree, committed code) on branch `alpha/adopt`; running it again there carries out the next step of `docs/alpha/adoption.md`, and where the hooks are off it switches them back on. `/alpha:extend <what to change>` changes a component or an install answer, `/alpha:specify <areas>` settles product areas, `/alpha:update` brings a project to a newer kit, and `/alpha:do <task>` works a task by a playbook from `skills/do/playbooks/`; a feature goes through research, a brainstorm and a spec and plan in `docs/alpha/features/<date>-<feature>/` that the user approves before any code. `/alpha:uninstall` and `/alpha:purge` run only when the user asks.

Optional: to stop Claude Code asking before each alpha CLI call during the interview, add `"Bash(<alpha checkout>/bin/alpha *)"` with the absolute path of this checkout to `permissions.allow` in `~/.claude/settings.json` (for an installed plugin, use the `bin/alpha` path the prompt shows).

Install it for every session from GitHub with `claude plugin marketplace add vs/alpha`, then `claude plugin install alpha@alpha`; update with `claude plugin marketplace update alpha` and `claude plugin update alpha@alpha`. `claude plugin validate .claude-plugin/marketplace.json` checks the manifests.

Recipes, defaults and the tool registry come from the plugin itself: the installed copy, or this checkout under `--plugin-dir`. Only `ALPHA_SOURCE` points alpha at another checkout; for a stack both have, that checkout's recipe wins.

The user's own layer is `~/.config/alpha/` (`ALPHA_CONFIG_DIR` overrides it; the tests point it at a temp folder): `overrides.toml` and `CHANGELOG.md` from `alpha defaults set`, and `recipes/` from `alpha recipe save`. It applies on top of the kit, and the kit's recipe wins for a stack both have. Nothing there is committed.

Kit tests: `uv run pytest` runs the fast suite. `uv run pytest -m slow` also bootstraps real projects with uv and pnpm (needs both installed and network access).
