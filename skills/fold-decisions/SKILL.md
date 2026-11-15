---
name: fold-decisions
description: Fold a project's decision records (docs/decisions/) into its docs and remove them, for a project an older alpha set up with records, so its decisions live in docs/specification.md, CONTRIBUTING.md, the answers' overrides and the Exceptions table. Use when alpha says the answers' decisions list is no longer part of the answers, or the user asks to fold, drop or migrate the decision records. Run as /alpha:fold-decisions [project].
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}/bin/alpha" *)
---

# Fold decisions

Move what a project's decision records still decide into the docs that say how the project is now, then remove the records and the answers' `decisions` list. alpha keeps no decision records: what the product does lives in `docs/specification.md`, how the work is done in `CONTRIBUTING.md`, principle changes in the answers' `overrides`, exceptions in CONTRIBUTING.md's Exceptions table, and when and why in git history.

Project: `$ARGUMENTS`

## 1. Check the project

`<target>` is the folder named above, else the current working directory.

- No `<target>/.claude/alpha/project.json` with a `manifest` key: alpha didn't generate or adopt it. Say so, and stop.
- Neither `<target>/docs/decisions/` nor a `decisions` key in project.json: nothing to fold. Say so, and stop.
- The tree must be clean (`git status --porcelain` prints nothing) and on a branch the project's rules allow work on (CLAUDE.md, Branching); otherwise say what to commit or switch first, and stop.

## 2. Sort every record

Read every file in `docs/decisions/` in full, oldest first. Put each in one group, and show the user the table (record, group, where it goes) before changing anything:

1. **Superseded.** Its status says superseded: drop it; the record that replaced it is sorted on its own.
2. **Already stated.** What it decides is already true in the generated docs, the answers or `docs/principles.toml` (an interview area's record, a choice the answers hold): drop it.
3. **An override.** It loosens, drops or tightens a principle (a `Principle:` line): check the answers' `overrides` holds it with its reason. If one is missing or has no reason, add the record's reason to that override with `/alpha:extend`.
4. **An exception.** It lets a file skip a check, keeps a baselined finding, or accepts a review finding: add a row to CONTRIBUTING.md's Exceptions table naming the path, the check (in backticks) and the record's reason. An accepted review finding of the past needs nothing: its review is over.
5. **A rule still in force.** Anything else a later change must follow. Write it, in present tense and without the history, into the doc it governs: what the product does into `docs/specification.md`, how the work is done into `CONTRIBUTING.md`. Put it outside the parts alpha generates (a sentence after a generated table, or a section of its own), so updates keep it.
6. **A dropped adoption step.** A step an older alpha dropped holds the record's number (`"decision": N`). Save `adoption` whole with `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '<object>'` (one line), that step's `decision` replaced by `"reason": "<the record's reason>"`.

Ask the user only about a record whose group isn't clear, or a product rule (group 5 into the specification); write the rest.

Before writing anything, run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers drop-decisions <target>`: alpha refuses every other change to the answers while their `decisions` list is there.

## 3. Remove the records

1. `git rm -r docs/decisions` in `<target>`.
2. `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target> --dry-run`, then without `--dry-run`, then `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" commit-update <target>`, so the generated docs list the overrides and exceptions and drop their links to records. Merge any proposal it leaves as `/alpha:extend` says.
3. Search the project for what still points at a record (`docs/decisions/`, `decision NNNN`, `ADR-`), in docs, code comments and CLAUDE.md's own sections, and point each at the doc that now holds the rule, or drop it.
4. Commit the docs changes and the removal as one `docs` commit whose body lists, per record, where its rule went.

## 4. Check

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" update <target> --dry-run` prints nothing to change, `docs/decisions/` is gone, and the project's checks pass. Tell the user where each kind of decision went, and that git history keeps the records (`git log --all -- docs/decisions`).
