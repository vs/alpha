---
name: grilling
description: Interview the user in rounds about a decision tree, recommending an answer for every question from the alpha kit defaults. Use whenever an alpha interview area asks the user to settle decisions, or the user wants their thinking about a project stress-tested.
---

<!-- Adapted from the `grilling` skill in mattpocock/skills (https://github.com/mattpocock/skills), MIT License, Copyright (c) 2026 Matt Pocock. -->

Interview the user until you reach a shared understanding. Map the decisions as a **design tree**: every decision branches into the decisions that hang off it.

## Rounds

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Word each question so "yes" accepts your recommended answer. Number questions across the whole interview (Q1, Q2, … keep counting in later rounds).

Each answer reshapes the tree: settled decisions push the frontier outward and unblock the questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round.

## Where recommendations come from

- Run `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults show --json` once per session and keep the result. Its `defaults` object holds the kit's preferred answers (the area skill names the key for each question, e.g. `defaults.review.max_lines`).
- Build on the project's earlier answers in `.claude/alpha/project.json`: a later question's recommendation follows from what the user already decided.
- When neither gives you a basis (a product name, say), draft a recommendation from what the user has told you so far, and say it is your suggestion.

## Facts are yours, decisions are the user's

Never ask the user for anything you can look up: installed tool versions, `git config user.name`, whether a folder exists, the latest stable version of a tool. Look it up yourself (dispatch a sub-agent for slow lookups). Only the questions downstream of a running lookup wait for it; ask the rest of the frontier now. Every _decision_ is the user's: put it to them and wait.

## When the user overrides a default

When the user's answer differs from a kit default:

1. Record it. A change to a principle (tighten, loosen or drop) goes in `overrides[]` as `{"principle", "scope", "change", "params", "reason"}`. Any other setting goes in the area's `decisions[]` entry: name the default in `context` and the choice in `decision`. Ask for the reason if the user hasn't given one.
2. Ask exactly: "Make this the default for future projects too?"
3. On yes, run:
   `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults set --key <dotted key> --value <value> --project <slug> --reason "<user's reason>" --trailer "<line>"`
   - `--key` is the defaults key the recommendation came from, without the `defaults.` prefix (e.g. `review.max_lines`, `identity.license`, `stacks.ml`).
   - `--value` is written as in TOML (`300`, `true`); plain words are stored as text.
   - `--project` is `identity.slug` from project.json.
   - Pass one `--trailer` per attribution line from this session's Claude Code attribution instructions (e.g. a `Co-Authored-By:` line), in that order. If there are none, pass no `--trailer`. Never invent co-author lines.
   - A principle override has no single key: don't run the command; record the wish as in step 4.
4. If the command exits 3, tell the user the defaults source isn't available on this machine, so the kit can't save a new default here. Add the wish to the area's decision `consequences`, e.g. "Wish: make review.max_lines = 300 the kit default (defaults source not available on this machine)." For any other failure, show the error and do what it says.
5. On no, the override stays in this project only.

## Done

The interview is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Summarize what was settled and wait for the user to confirm you share an understanding before acting on it.
