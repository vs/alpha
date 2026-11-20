# Install: an existing repo

Bring an existing repo up to alpha's principles without stopping its work: alpha's files go in on the branch `alpha/adopt`, today's findings are baselined so only new ones fail, and a compliance plan lists the rest, one step at a time. alpha's CLI writes only its own files; reworking app code is ordinary work done under the project's new hooks. The rules of `SKILL.md` beside this file hold throughout. Send `adoption`, `areas` and `overrides` whole with each `answers write`.

## 1. Resume

When `<target>/.claude/alpha/project.json` has an `adoption` key, an adoption is under way: report which areas are done, then go on at the first step not finished (step 4 while an install area is pending, else step 5). When every install area is done, finish a product area marked `in_progress`, then offer the ones after the last product area settled, in `new-project.md` step 3's order (all of them when none is settled); an area before it was already offered. Then go on to step 5. Otherwise start at step 2.

## 2. Survey

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt survey <target> --save`. If it refuses, show its message and stop.

Then save the start, keeping what the survey saved in `adoption`:
`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"schema": 1, "areas": {…the install areas "pending", the product areas "open", as new-project.md step 1…}, "overrides": [], "adoption": {…the saved adoption…}}'`

Tell the user in a few lines what the survey found: candidate components and stacks, CI, docs, hook managers, and how many recent commits follow the convention. A repo with docs and no code yet has no candidates: say that alpha generates the skeleton of each component the interview settles.

## 3. Defaults

As `new-project.md` step 2: run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults show --json`, keep `defaults`, and say where they come from.

## 4. Interview

Run the install areas in `SKILL.md`'s order from their guides, `<target>` as the target, moving on only after each check prints `ok`. After the install areas, offer the product areas as `new-project.md` step 3 says, with one change: recommend Settle now for an area the repo's docs describe (a path in `documentation.existing`, or a doc the survey found), naming the doc, and Skip for now for the rest. These rules win over the guides' own:

- Recommend what the repo already does when it meets the principle, else the kit default; say which it is. Never ask what the survey or the repo's files answer: read the README for identity, the manifests, lockfiles and CI for components and build, `LICENSE` for `identity.license_file` (keep the repo's license).
- Where the repo falls short of an active principle, say so in one line and note it as a gap for step 5. Change no app code during the interview.
- Components: start from the survey's candidates, and add the parts the repo's docs describe that have no code yet. A candidate in an examples, fixtures or reference-data folder goes into `not_code` instead (the guide's Not code question); after saving it, run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt survey <target> --save` again, which then leaves those folders out. A component whose folder holds code gets an adopted recipe, with or without a manifest, drafted with `alpha:stack-recipe` (named `<component>-<stack>`, extending the kit's recipe when the repo's tools are the kit's). Prove each with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe try <target> <recipe>`; each check it reports with findings goes into `adoption.baselines` as `<step>:<component>`.
- A component with no project structure yet (its folder is missing or holds only docs) has no tools to adopt; never write its files yourself. Ask, recommending yes: "<component> has no project structure yet. Generate alpha's <stack> skeleton for it in <path>?" On yes, set its `stack` to the kit's recipe (`recipe list` names it), or to one `alpha:stack-recipe` drafts and proves. It gets no adopted recipe and no baselines; step 7 writes its manifest, strict settings and setup test and commits them. A component at the repository root: after step 7.4, commit what its bootstrap made beyond the lockfile, as that step's note says. On no, leave it out and say `/alpha:update` adds it later; if no component is left, say alpha has nothing to enforce there yet, and stop.
- Git history: set `adoption.git_hooks` to `alpha` when the survey found no hook manager and no `hooks_path`, else `chain` (the repo's manager stays in charge and calls alpha's check between `# alpha:begin` and `# alpha:end` lines). Commits already in history stay as they are.
- Documentation: where the repo already has a doc for an area alpha writes (architecture, a glossary, a dependency log), record its path in `documentation.existing`, so alpha's file refers to it instead of repeating it.
- Repository checks: offer to baseline the ones the repo likely fails today (`typos`, `markdown`, `links`, `agent-config`, `actions`) by adding them to `adoption.baselines`.

## 5. Assessment

Dispatch one general-purpose subagent with the Agent tool. Its prompt: read `${CLAUDE_PLUGIN_ROOT}/project-files/skills/audit/SKILL.md` and follow its lenses over `<target>`, judged against every active principle in the kit defaults and the answers in project.json, with no limit on findings and no code changes; return a JSON list of findings, each `{"principle", "component", "title", "why", "evidence": "<file:line>", "severity": "must|should|nice", "acceptance": "<a command that would pass once fixed, preferably a test to add>"}`.

Leave out findings about the product's specification (open questions, proposals and gaps in the product docs): they aren't compliance work; keep them for step 8's report. Group the remaining findings with the gaps from step 4. With `alpha:grilling`, ask the user about each must and should finding, recommending a phase: P4 for rework, P6 for linking acceptance checks to tests, P3 only to move a component to the kit's own tool. Save the confirmed ones as steps in `adoption.steps` (each `{"id", "phase", "title", "why", "component", "principles", "acceptance": [{"run": "…"}], "status": "pending"}`; use `{"confirm": "…"}` only when no command can prove it), then run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt gaps <target> --save` to add the mechanical steps.

## 6. Preview and confirm

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json` (must print `ok`) and `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" apply <target> --dry-run`. Show, in plain words: the areas' answers as `new-project.md` step 4 does; the files alpha adds, merges and must merge by hand (each `conflict`); the components whose skeleton it generates (the `New components` line); the baselines and their counts from the recipe proofs; and the plan by phase. Ask: "Install alpha on branch alpha/adopt with these answers?" and wait for a clear yes.

## 7. Install

In order:

1. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" apply <target>`. It switches to `alpha/adopt`, and never overwrites a file the repo already has.
2. For each `<path>: merge by hand; proposal: …` line, read the proposal (the repo's version and alpha's) and edit the real file to keep every line of the repo's and add alpha's: never just alpha's side. For CI, keep the repo's jobs and add alpha's. Show the user each result. In chain mode, add alpha's call to the hook manager's commit-msg hook, between `# alpha:begin` and `# alpha:end` lines, as the apply note says.
3. Tell the user this installs toolchains (a new component's too), records today's findings as baselines and runs every check, then run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" bootstrap <target> --capture-baselines`. A secret it finds: ask the user to rotate it and add a P0 step; a false positive goes in `.betterleaksignore`. A known vulnerability: upgrade it, or, with the user's yes, add an `osv-scanner.toml` exception with a reason and a review date.
4. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" commit <target> --trailer "<line>"` with one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits. Never invent co-author lines.

## 8. Report

Tell the user: the commits on `alpha/adopt`; what is enforced now (as `new-project.md` step 6, plus: only new findings fail; baselines shrink as findings are fixed and never grow without an Exceptions row in CONTRIBUTING.md); the baselines (`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" baseline show <target>`); the plan's phases with step counts (`docs/alpha/adoption.md`); the open product areas, each with its `/alpha:update <area>` request, and the specification findings step 5 left out; what wasn't checked. Pushing and opening the pull request are theirs to do, or ask whether you should. Next: alpha's hooks and settings load only when a session starts, so this session still runs without them. Start a new Claude Code session in `<target>` (with the same plugin flags), and run `/alpha:install` there to begin the plan's first step.

## The plan

In an adopted repo with steps left, `/alpha:install` carries out one step per run, unless the user asks for more.

1. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt next <target>` names the step, why, what proves it done, and its branch. Tell the user in two lines.
2. Branch: `git switch -c <branch>` from the default branch, or from `alpha/adopt` while that isn't merged. Then `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt start <target> <id>`.
3. Do the work under the project's hooks and rules, in commits per the convention. Write the tests a step's acceptance names. A fixed baselined finding tightens its baseline when its check runs (or run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" baseline tighten <target>`); commit the baseline file with the fix.
4. When the step changes the answers, save them before checking it: a recipe change (a new tool, a check turned on) means sending `recipes` whole with `answers write` and proving it with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe try <target> <recipe>`; an emptied baseline means sending `adoption` whole without that id in `baselines` and `git rm` its file; a new tool with legacy findings means adding its check id there. Then run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target>` (it rewrites the commands, CI and principles to match), `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" baseline capture <target> --all` for a newly listed check, and `commit` as in step 7.
5. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt done <target> <id>` must pass; add `--confirmed-by-user` only after the user confirmed each `confirm` condition. Never set a step's status any other way. Then `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target>` and `commit` again, so `docs/alpha/adoption.md` shows it.
6. A step that turns out wrong or not worth it: agree why with the user, then `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt drop <target> <id> --reason "<why>"`; `docs/alpha/adoption.md` shows the reason.

Report what changed, the commits, and the next step.
