---
name: adopt
description: Bring an existing repo under alpha - survey it, interview every area with the repo's own practice as the recommendations, install alpha's enforcement on a branch with baselines for legacy findings, and write a compliance plan; run again in an adopted repo to carry out the plan's next step. Run as /alpha:adopt [folder].
disable-model-invocation: true
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Adopt

Bring an existing repo up to alpha's principles without stopping its work: alpha's files go in on a branch, today's findings are baselined so only new ones fail, and a compliance plan lists the rest, one step at a time. alpha's CLI writes only its own files; reworking app code is ordinary work you do under the project's new hooks.

Folder argument: `$ARGUMENTS`

Save answers only with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '<object>'` on one line, the JSON typed straight into the command, never a heredoc or a python3 script. Each top-level key replaces that key in project.json, so send `adoption`, `areas`, `decisions` and `overrides` whole.

## 1. Target and mode

`<target>` is the folder given above (expand `~`, resolve it), else the current working directory. Read `<target>/.claude/alpha/project.json`:

- A `manifest` with `adopted_at`: the repo is adopted. Go to step 9.
- A `manifest` without `adopted_at`: alpha generated it. Invoke `alpha:extend` with the Skill tool for any change, and stop here.
- An `adoption` key: an adoption is under way. Report which areas are done, then go on at the first step not finished (step 4 while an area is pending, else step 5).
- Anything else: start at step 2.

## 2. Survey

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt survey <target> --save`. If it refuses, show its message and stop. If `git.clean` is false, tell the user alpha installs onto committed code only, list `git.dirty`, and stop until they commit or stash.

Then save the start, keeping what the survey saved in `adoption`:
`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"schema": 1, "areas": {…every area as in /alpha:new-project, all "pending"…}, "overrides": [], "decisions": [], "adoption": {…the saved adoption…}}'`

Tell the user in a few lines what the survey found: candidate components and stacks, CI, docs and decision records, hook managers, and how many recent commits follow the convention.

## 3. Defaults

As `/alpha:new-project` step 3: run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults show --json`, keep `defaults`, and say where they come from.

## 4. Interview

Run every area in `/alpha:new-project`'s order, invoking each area's skill with the Skill tool, `<target>` as its target: `alpha:identity`, `alpha:components`, `alpha:architecture`, `alpha:errors`, `alpha:testing`, `alpha:ui`, `alpha:documentation`, `alpha:build-and-hosting`, `alpha:security`, `alpha:dependencies`, `alpha:observability`, `alpha:releases`, `alpha:data`, `alpha:accessibility`, `alpha:performance`, `alpha:git-history`, `alpha:agent-workflow`. Move on only after its check prints `ok`. These rules win over the area skill's own:

- Recommend what the repo already does when it meets the principle, else the kit default; say which it is. Never ask what the survey or the repo's files answer: read the README for identity, the manifests, lockfiles and CI for components and build, `LICENSE` for `identity.license_file` (keep the repo's license).
- Where the repo falls short of an active principle, say so in one line and note it as a gap for step 5. Change no app code during the interview.
- Components: start from the survey's candidates. Every component gets an adopted recipe drafted with `alpha:stack-recipe` (named `<component>-<stack>`, extending the kit's recipe when the repo's tools are the kit's). Prove each with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" recipe try <target> <recipe>`; each check it reports with findings goes into `adoption.baselines` as `<step>:<component>`.
- Git history: set `adoption.git_hooks` to `alpha` when the survey found no hook manager and no `hooks_path`, else `chain` (the repo's manager stays in charge and calls alpha's check). Commits already in history stay as they are.
- Documentation: an existing decision-record folder keeps its numbers; alpha's records follow them.
- Repository checks: offer to baseline the ones the repo likely fails today (`typos`, `markdown`, `links`, `agent-config`, `actions`) by adding them to `adoption.baselines`.

## 5. Assessment

Dispatch one general-purpose subagent with the Agent tool. Its prompt: read `${CLAUDE_PLUGIN_ROOT}/project-files/skills/audit/SKILL.md` and follow its lenses over `<target>`, judged against every active principle in the kit defaults and the answers in project.json, with no limit on findings and no code changes; return a JSON list of findings, each `{"principle", "component", "title", "why", "evidence": "<file:line>", "severity": "must|should|nice", "acceptance": "<a command that would pass once fixed, preferably a test to add>"}`.

Group the findings with the gaps from step 4. With `alpha:grilling`, ask the user about each must and should finding, recommending a phase: P4 for rework, P6 for linking acceptance checks to tests, P3 only to move a component to the kit's own tool. Save the confirmed ones as steps in `adoption.steps` (each `{"id", "phase", "title", "why", "component", "principles", "acceptance": [{"run": "…"}], "status": "pending"}`; use `{"confirm": "…"}` only when no command can prove it), then run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt gaps <target> --save` to add the mechanical steps.

## 6. Preview and confirm

Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json` (must print `ok`) and `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt apply <target> --dry-run`. Show, in plain words: the areas' answers as `/alpha:new-project` step 5 does; the files alpha adds, merges and must merge by hand (each `conflict`); the baselines and their counts from the recipe proofs; and the plan by phase. Ask: "Install alpha on branch alpha/adopt with these answers?" and wait for a clear yes.

## 7. Install

In order; if a step fails, show its message, fix the cause with the user, and rerun that step:

1. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt apply <target>`.
2. For each `<path>: merge by hand; proposal: …` line, read the proposal (the repo's version and alpha's) and edit the real file to keep every line of the repo's and add alpha's: never just alpha's side. For CI, keep the repo's jobs and add alpha's. Show the user each result.
3. Tell the user this installs toolchains, records today's findings as baselines and runs every check, then run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" bootstrap <target> --capture-baselines`. A secret it finds: ask the user to rotate it and add a P0 step; a false positive goes in `.betterleaksignore`. A known vulnerability: upgrade it, or, with the user's yes, add an `osv-scanner.toml` exception with a reason and a review date.
4. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" commit-update <target> --trailer "<line>"` with one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits. Never invent co-author lines.

## 8. Report

Tell the user: the commits on `alpha/adopt`; what is enforced now (as `/alpha:new-project` step 7, plus: only new findings fail; baselines shrink as findings are fixed and never grow without a decision); the baselines (`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" baseline show <target>`); the plan's phases with step counts (`docs/adoption.md`); what wasn't checked. Pushing and opening the pull request are theirs to do, or ask whether you should. Next: run `/alpha:adopt` again to start the first step.

## 9. The plan

One step per run, unless the user asks for more.

1. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt next <target>` names the step, why, what proves it done, and its branch. Tell the user in two lines.
2. Branch: `git switch -c <branch>` from the default branch, or from `alpha/adopt` while that isn't merged. Then `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt start <target> <id>`.
3. Do the work under the project's hooks and rules, in commits per the convention. Write the tests a step's acceptance names. Change a recipe through `/alpha:extend` and re-prove it with `recipe try`; a fixed baselined finding tightens its baseline (`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" baseline tighten <target>`), and a cleared baseline leaves `adoption.baselines` through `/alpha:extend`.
4. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt done <target> <id>` must pass; add `--confirmed-by-user` only after the user confirmed each `confirm` condition. Never set a step's status any other way.
5. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target>`, then `commit-update` as in step 7, so `docs/adoption.md` shows it.
6. A step that turns out wrong or not worth it: record why with the user through the project's `/decision` skill (naming the step id in backticks), then `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" adopt drop <target> <id> --decision <number>`.

Report what changed, the commits, and the next step.
