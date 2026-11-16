# Session pickup

You own the resume point. The earlier session's trail is input you build on, not something to redo.

1. Find the trail: the resume notes in `.claude/alpha/notes/resume-<branch>.md` (each `/` in the branch written as `-`) of every checkout `git worktree list` names (the Pause playbook writes one, and the folder isn't shared between worktrees); resume in the checkout that holds the note. Then the branch and its commits since the default branch (`git log <main>..`, `git diff <main>...`, `<main>` the first of `origin/HEAD`, `origin/main`, `origin/master`, `main`, `master` that exists; trunk-based, the commits since the last push), uncommitted changes, the stash the note names, the spec in `docs/alpha/features/`, and what the branch changed in `docs/alpha/specification.md` and `CONTRIBUTING.md`. A transcript or pull request the user names counts too; read a long one in a subagent and keep its timeline.
2. Rebuild the state: what landed, what is written but uncommitted, what was decided, what was planned next. Apply the stash the note names: find the line in `git stash list` that holds its message and pop that entry's current `stash@{n}`; it holds the step that failed the checks.
3. Name the resume point: what's done, what's left, and the first step. Don't re-run finished work or re-decide what was settled.
4. Check the claims the rest of the work rests on against the real thing: run the tests and the repro the trail says pass. A "done" in a note is not proof.
5. Hand the rest to the playbook the work was in, from its next step. Delete the resume note once that playbook finishes, so a later pickup doesn't read it.

**Reply:** where the earlier session stopped, what you inherited and what (ideally nothing) you redid, the resume point, and the outcome.
