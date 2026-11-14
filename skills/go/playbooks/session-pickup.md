# Session pickup

You own the resume point. The earlier session's trail is input you build on, not something to redo.

1. Find the trail: the resume notes in `.claude/alpha/notes/resume-<branch>.md` of every checkout `git worktree list` names (the Pause playbook writes one, and the folder isn't shared between worktrees); resume in the checkout that holds the note. Then the branch and its commits since main (`git log main..`, `git diff main...`), uncommitted changes, the spec in `docs/specs/`, and the decision records added on the branch. A transcript or pull request the user names counts too; read a long one in a subagent and keep its timeline.
2. Rebuild the state: what landed, what is written but uncommitted, what was decided, what was planned next.
3. Name the resume point: what's done, what's left, and the first step. Don't re-run finished work or re-decide what was settled.
4. Check the claims the rest of the work rests on against the real thing: run the tests and the repro the trail says pass. A "done" in a note is not proof.
5. Hand the rest to the playbook the work was in, from its next step.

**Reply:** where the earlier session stopped, what you inherited and what (ideally nothing) you redid, the resume point, and the outcome.
