# Refactoring

You own the contract. The structure changes; the behavior doesn't. A refactoring that reveals a bug or a missing feature ships first, on its own, then that work follows its own playbook.

1. Pin the behavior before anything moves. Run Investigation steps 1 and 2 over the code to learn its contract, then make sure a test fails when that behavior breaks: the existing tests if they do, or a characterization test (one that records what the code does today) where they don't. Type checks and lint are not a pin.
2. Name the target shape: the module layout, types and call graph as you'd build them today. It must remove branches, states or layers, not add indirection. Code whose shape is already clear and local stays.
3. Subtract first: delete dead code, one-caller wrappers, redundant checks and stale references before the new shape goes in (`subtract-first`).
4. Move in small steps that each keep the pin green. A new internal API replaces the old one in the same change: every caller migrated, the old one deleted, no compatibility layer. Check every rename against the files, including strings, docs and config a symbol search misses.
5. Prove behavior is unchanged on the real thing, not only by the tests: run the CLI or the app the same way before and after, or diff their outputs.
6. Keep it only if it's easier to read: fewer layers between a question and its answer, less state to hold in your head (`lean-structure`). Otherwise revert it.
7. Finish with Done (SKILL.md section 3): a subtraction commit, then the reshape, each green on its own.

**Reply:** the structure that changed, the pin it was held against, the proof behavior is unchanged, what got simpler, and what was reverted. No new behavior.
