# Not-code folders: plan

Built native on 2026-11-20. Tasks run in order; each is one commit that passes `mise run check`. Task 2 needs task 1's principles key, and tasks 3 to 5 read it, so none runs side by side.

## 1. The not_code answer and its render

`feat(alpha): Add not-code folders to the answers`

- `src/alpha/answers.py`: `Answers.not_code`, `_COMPONENTS_FIELDS`, `_TOP_KEYS`, parsing with `validate.relative` and the covers-a-component check.
- `src/alpha/principles.py`: top-level `not_code`.
- `src/alpha/render/docs.py`: the line in CLAUDE.md's Commands and CONTRIBUTING.md's Components.
- `docs/specification.md`: R17.1, the Answers section.
- Tests: F1, F2.

## 2. The hooks skip not-code files

`feat(hooks): Leave not-code folders to secrets checks`

- `project-files/hooks/_common.py`: `not_code`.
- `project-files/hooks/post_edit.py`, `stop_checks.py`, `guard_paths.py`.
- `docs/specification.md`: Hooks and checks.
- Tests: F3, F4, F5.

## 3. The review leaves them out

`feat(hooks): Leave not-code files out of the review`

- `project-files/hooks/review.py`: `brief`, `gate`.
- `docs/specification.md`: Review, files to review.
- Tests: F6.

## 4. The survey skips them

`feat(alpha): Skip not-code folders in the survey`

- `src/alpha/adopt.py`: `survey`.
- Tests: F7.

## 5. The components guide asks for them

`feat(alpha): Ask for not-code folders at install`

- `skills/install/areas/components.md`; `skills/install/adopt.md` where it reads survey candidates, if it names them.
- Tests: F8.

This repo's own copies under `.claude/alpha/` follow in the release PR's `alpha update`, as earlier hook changes did.
