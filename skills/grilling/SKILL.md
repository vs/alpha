---
name: grilling
description: Interview the user in rounds about a decision tree, recommending an answer for every question from the alpha kit defaults. Use whenever an alpha interview area asks the user to settle decisions, or the user wants their thinking about a project stress-tested.
---

<!--
Adapted from the `grilling` skill in mattpocock/skills (https://github.com/mattpocock/skills).

MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->

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
- Build on the project's earlier answers in `<target>/.claude/alpha/project.json` (`<target>` is the folder the interview is setting up): a later question's recommendation follows from what the user already decided.
- When neither gives you a basis (a product name, say), draft a recommendation from what the user has told you so far, and say it is your suggestion.

## Facts are yours, decisions are the user's

Never ask the user for anything you can look up: installed tool versions, `git config user.name`, whether a folder exists, the latest stable version of a tool. Look it up yourself (dispatch a sub-agent for slow lookups). Only the questions downstream of a running lookup wait for it; ask the rest of the frontier now. Every _decision_ is the user's: put it to them and wait.

## When the user overrides a default

When the user's answer differs from a kit default:

1. Record it. Ask for the reason if the user hasn't given one.
   - A change to a principle goes in `overrides[]` as `{"principle", "scope", "change", "params", "reason"}`: `principle` is an id from `defaults.principles[].id`; `scope` is `"project"` or `"component:<name>"`; `change` is `"tighten"`, `"loosen"` or `"drop"`; `params` holds any changed parameters (`{}` if none); `reason` is required for `loosen` and `drop`.
   - Any other setting goes in the current area's `decisions[]` entry: name the default in `context` and the choice in `decision`.
2. Ask exactly: "Make this the default for future projects too?"
3. On yes, for a setting, run:
   `"${CLAUDE_PLUGIN_ROOT}/bin/alpha" defaults set --key <dotted key> --value <value> --project <slug> --reason "<user's reason>" --trailer "<line>"`
   - `--key` is the defaults key the recommendation came from, without the `defaults.` prefix (e.g. `review.max_lines`, `identity.license`, `stacks.backend`).
   - `--value` is written as in TOML (`300`, `true`); plain words are stored as text.
   - `--project` is `identity.slug` from project.json.
   - Pass one `--trailer` per attribution line from this session's Claude Code attribution instructions for commits, in that order. If there are none, pass no `--trailer`. Never invent co-author lines.
4. Read the exit code. Never tell the user a default was saved unless the command exits 0.
   - If it exits 0, tell the user the new default is saved for their next project.
   - If it exits 4, tell the user the defaults source isn't available on this machine, so the kit can't save a new default here. Add the wish to the current area's decision `consequences`, e.g. "Wish: make review.max_lines = 300 the kit default (defaults source not available on this machine)."
   - If it exits 3, show the user its message and follow the fix it names, then run it again.
5. On yes for a principle override: the kit can't save principle defaults yet; note the wish in the current area's decision `consequences`.
6. On no, the override stays in this project only.

## Done

The interview is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Summarize what was settled and wait for the user to confirm you share an understanding before acting on it.
