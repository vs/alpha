---
name: debt
description: List every deliberate shortcut in this project (`shortcut:` comments) as a debt ledger, with the limit each one names and when to upgrade it. One-shot report that changes nothing. Use for /debt, "what did we defer", "list the shortcuts", or before planning work that might cross a shortcut's limit.
allowed-tools: Bash(python3 .claude/alpha/checks/shortcuts.py *)
---

<!--
Adapted from the `ponytail-debt` skill in DietrichGebert/ponytail (https://github.com/DietrichGebert/ponytail).

MIT License

Copyright (c) 2026 DietrichGebert

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

# Shortcut debt

A deliberate shortcut is marked in the code with `shortcut: <the limit>, <when to upgrade>`, a comment the code-over-comments principle allows. This skill collects them into one ledger, so a deferral can't quietly become permanent. The `shortcuts` repository check already fails on a marker that names no upgrade trigger.

## Scan

Run, from the project root:

```sh
python3 .claude/alpha/checks/shortcuts.py --list
```

It prints one row per marker, `<file>:<line>, limit: <the limit>. upgrade: <when to upgrade>.`, a `no-trigger` row for a marker without one, and a count.

## Report

Group the rows by file. For each, say in plain words what was simplified (read the code around the marker) and whether the project's expected load (`docs/performance.md`) or a recent change already crosses the limit; mark those rows **due**. Add an owner per row only if the user asks (`git blame -L<line>,<line> <file>`).

End with the count line. Nothing found: "No shortcuts. Clean ledger."

## Boundaries

Reads and reports only; changes nothing. On request, write the ledger to a file the user names.
