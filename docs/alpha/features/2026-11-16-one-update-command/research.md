# One update command: research

Date: 2026-11-16

## The code today

- `skills/update/SKILL.md` brings alpha's files to the answers and the kit: `update --dry-run`, confirm, `update`, merge each proposal by hand, bootstrap new components, `commit`.
- `skills/extend/SKILL.md` changes a component or an install area's answer: it reads the area's guide in `skills/install/areas/`, re-asks only what the change affects, keeps `overrides` whole, then runs the same loop as update, plus the "Revisit the area" and "Fix project.json" loop. A product area request points to `/alpha:specify` (`skills/extend/SKILL.md:28`).
- `skills/specify/SKILL.md` settles product areas from `skills/specify/areas/`: research, two or three options, grilling, `done`, then the same loop.
- The three skills share the loop; only the step that changes the answers differs. The CLI (`alpha update`) already merges both kinds of answer change and a kit upgrade in one run (R4.1, R7.1, R11.1, R11.2), so no Python logic changes.
- Install never settles a product area (`skills/install/SKILL.md:33`, R5.2, R7.2). `answers check` refuses an install area left open (R5.1) but accepts a product area that is `done`.
- `/alpha:specify` and `/alpha:extend` are named in rendered project docs (`src/alpha/render/area_docs.py:23-34`, `src/alpha/render/docs.py:304,486`), CLI messages (`src/alpha/answers.py:433,1181`, `src/alpha/core_areas.py:417`, `src/alpha/adopt.py:56`), the palette check (`project-files/checks/palette.py:189,202`), the copied decision skill (`project-files/skills/decision/SKILL.md:14-26`), the `performance-budgets` statement (`defaults/defaults.toml:402`), `do` and its feature playbook, README and `docs/specification.md`.

## How other tools do it

| Tool | Shape | What it shows |
|---|---|---|
| Copier | `copier update` re-applies a newer template; `copier update --defaults --data key=value` changes one answer and keeps the rest; `--vcs-ref` changes answers without a template upgrade; `copier recopy` re-applies without the smart merge. ([docs](https://copier.readthedocs.io/en/latest/updating/)) | One update command both syncs the template and changes chosen answers. The answers file is never edited by hand, since that would break the merge base. |
| cruft | `cruft update` syncs a cookiecutter template; `--variables-to-update '{…}'` changes chosen variables in the same run. A known gap: once in sync, it doesn't re-ask a variable. ([repo](https://github.com/cruft/cruft), [PyPI](https://pypi.org/project/cruft)) | The same single-command shape; changing an answer has to be a request of its own, not a side effect of re-running. |
| Claude Code skills | `$ARGUMENTS` carries the whole request; a skill with several jobs is commonly a short router in SKILL.md that hands each job to its own file. Conditional loading of sections is only a feature request. ([issue](https://claudeissues.com/issue/49090-feature-conditional-section-loading-in-skills-based-on-arguments)) | A router plus per-job files keeps each run's context small. alpha's area guides already are those per-job files. |

## Options

| Option | Cost | Rules out |
|---|---|---|
| One `update` skill routing on its request to sync, change or settle, reading the area guides (chosen) | One skill to rewrite; two deleted; pointers renamed; a breaking release (2.0.0) | Separate entry points for the three jobs |
| Keep three skills, make `update` forward to the others | Nothing deleted; the user still sees three commands | The single command the user asked for |
| Per-job files beside the update skill (`sync.md`, `change.md`, `settle.md`) | Three more files to keep in step | Nothing; but each job is a few lines once the guides hold the questions |
