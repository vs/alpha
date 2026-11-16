# Releases

## Before you start

`/alpha:install` reads this guide for a new project's or an adoption's interview, and `/alpha:extend` when a change revisits this area. `<target>` is their target folder; the answers live in `<target>/.claude/alpha/project.json`. Their rules win over this guide's where they differ. When the user asks to revisit this area outside them, run `/alpha:extend` with the request.

## Purpose

Users and other components need to know what changed and whether an upgrade is safe. This area settles how versions are numbered, where changes are written up, and how a release is cut. Every project gets a Releases section in `CONTRIBUTING.md`, plus `CHANGELOG.md` when the changelog is kept in a file.

## Fields this area settles

- `releases.scheme` - `"semver"`, `"calver"` or `"none"` (every commit on main is a release, e.g. a continuously deployed service).
- `releases.changelog` - `"file"` (`CHANGELOG.md`), `"github-releases"` or `"none"`.
- `releases.scope` - `"repo"` (one version for everything) or `"component"` (each component versioned on its own; only with more than one component).
- `releases.process` - one or two sentences on how a release is cut, e.g. "Tag vX.Y.Z on main; CI builds and publishes the package."
- `areas.releases` - `"in_progress"` while you work, `"done"` at the end.

## Questions

Run these with the `alpha:grilling` skill (invoke it with the Skill tool and follow it), as one round:

- **Scheme** - recommend `defaults.releases.scheme` for anything others install or call (a library, a CLI, an API); `calver` suits releases tied to dates or model promotions; `none` suits a service deployed on every merge. Without version numbers there are no tags, so `none` goes with scope `repo` and a changelog that is a `file` (by date) or `none`.
- **Changelog** - recommend `defaults.releases.changelog`. Explain: a file travels with the code and works offline; GitHub releases suit binaries attached to each release.
- **Scope** - ask only with more than one component: recommend `defaults.releases.scope` when the components ship together, `component` when they're published separately (e.g. a library and an app). With one component, save `"repo"` without asking.
- **Process** - draft it from the build area (CI provider, each component's artifact and hosting), e.g. "Tag vX.Y.Z on main; CI builds the container and deploys it", and ask the user to confirm or correct it.

When an answer differs from a default, follow the grilling skill's override protocol (keys `releases.scheme`, `releases.changelog`, `releases.scope`).

## Writing the answers

Save every change with one call, the JSON object on one line in single quotes (write each `'` inside it as `'\''`):

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers write <target> --json '{"areas": {…every area, with "releases": "in_progress"…}}'`

Each top-level key you send replaces that key in project.json; the others stay as they are. So always send `areas` whole, with the entries you aren't changing kept. Never edit project.json directly.

1. Read `<target>/.claude/alpha/project.json`.
2. When you start asking, save `areas` with `releases` set to `"in_progress"`.
3. When the user confirms the area, save the `releases` object `{"scheme", "changelog", "scope", "process"}`. Keep the exact field names.
4. In the same call, save `areas` with `releases` set to `"done"`.

## Check

Run:

`"${CLAUDE_PLUGIN_ROOT}/bin/alpha" answers check <target>/.claude/alpha/project.json --area releases`

It prints `ok`, or one problem with its fix. Fix project.json (ask the user when the fix needs a decision) and re-run until it prints `ok`.
