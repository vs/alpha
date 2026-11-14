# Investigation

You own the answer. The work is read-only: a cited explanation or a recommendation, no code change.

1. Pin the question in one sentence. When it's really "should we do X or Y", the answer is a recommendation with its tradeoffs.
2. Map how it works. Find the entry points, then trace the real flow end to end: where data comes in, what it passes through, what is stored, what goes out. Cite `file:line` for every step. For a wide area, give each subagent one slice and merge their maps yourself.
3. Find why it's built this way, when the question asks: the decision records and `docs/specs/` first, then `git log -S <symbol>`, `git blame` on the lines that matter, and the pull requests behind those commits (`gh pr view`). Cite the record, commit or pull request.
4. Check the answer against the running code where a claim is cheap to run: call the function, run the command, print the value.
5. Write it up as Overview, Key concepts, How it works, Where things live, Gotchas. A recommendation gets a table of the options, what each costs and breaks, and your pick with its reason.

A search that finds nothing is an answer: say what you searched. Never make up a caller, an API or a reason. When the question turns out to need a change, end with the playbook that change takes (Feature, Bug fix, Refactoring) and stop.

**Reply:** the write-up. For "are we sure?", your real judgment with its reasons; push back when the premise is wrong.
