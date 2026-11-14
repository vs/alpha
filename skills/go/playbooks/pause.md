# Pause

You own a clean stop: leave what a fresh session needs to resume without you. Only on an explicit pause; "keep going" or "don't stop" means don't pause.

1. Stop at a safe point: finish the current small step or back out of it. Start nothing new, and stop any subagents.
2. Commit only what passes the checks, following the commit skill. Leave the rest uncommitted in the working tree; never commit broken work to get it saved, and never push or open a pull request to pause. The Stop hook checks uncommitted files too and blocks a stop on failing ones, so back out a step that fails the checks (step 1 allows it) and describe it in the resume note instead.
3. Write the resume note to `.claude/alpha/notes/resume-<branch>.md` (generated projects git-ignore that folder; when `git check-ignore` says it isn't, add `.claude/alpha/notes/` to `.gitignore` in its own commit, the line a later kit's `alpha update` writes): the goal, the playbook and the step you're on, what's done and verified, what's written but unchecked, the next steps, the files that matter, and the traps you found. Point to the spec and decision records instead of repeating them.

**Reply:** where you stopped, what's committed and what's uncommitted (paths, no diffs), the resume note's path, and the first step on resume.
