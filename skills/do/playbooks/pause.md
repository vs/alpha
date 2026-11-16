# Pause

You own a clean stop: leave what a fresh session needs to resume without you. Only on an explicit pause; "keep going" or "don't stop" means don't pause.

1. Stop at a safe point: finish the current small step or back out of it. Start nothing new, and stop any subagents.
2. Commit only what passes the checks, following the commit skill. Leave the rest uncommitted in the working tree; never commit broken work to get it saved, and never push or open a pull request to pause. The Stop hook checks uncommitted files too and blocks a stop on failing ones, so save a step that fails the checks with `git stash push --include-untracked -m "resume <branch>: <step>" -- <paths>`, which also backs it out (step 1 allows it), and name the stash in the resume note.
3. Write the resume note to `.claude/alpha/notes/resume-<branch>.md`, each `/` in the branch written as `-` (alpha's `.gitignore` ignores that folder; when `git check-ignore` says it isn't, add `.claude/alpha/notes/` to `.gitignore` in its own commit): the goal, the playbook and the step you're on, what's done and verified, what's written but unchecked, the stash that holds a step backed out, the decisions the user made that no doc holds yet, the next steps, the files that matter, and the traps you found. Point to the spec and the docs instead of repeating them.

**Reply:** where you stopped, what's committed and what's uncommitted (paths, no diffs), the resume note's path, and the first step on resume.
