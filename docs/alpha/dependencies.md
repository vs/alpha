# Dependencies

## Policy

- Adding: every new dependency gets a row in the log below, with the reason. The Stop hook blocks a lockfile change that adds a direct dependency without one (it reads uv.lock and Cargo.lock; in any other lockfile every change counts); upgrades, removals and the packages they pull in need none.
- Pinning: lockfiles pin every version. Only the package manager changes them; Claude can't edit them by hand.
- Upgrading: Dependabot opens weekly update pull requests, per component and for the CI actions.

## Log

Log every dependency added, with the reason.

| Dependency | Component | Why | Added |
|---|---|---|---|
| deptry | alpha | Unused, missing and transitive dependencies (the structure check). | 2026-11-16 |
| pyright | alpha | Strict type checking. | 2026-11-16 |
| pytest | alpha | Test runner. | 2026-11-16 |
| pytest-xdist | alpha | Runs the suite in four workers (`-n 4` in addopts), so about 1,900 tests finish in a few minutes. | 2026-11-16 |
| pyyaml | alpha | Tests parse the YAML alpha's own `yaml_write` emits (CI workflows, Dependabot) to check it round-trips; alpha itself writes YAML without it. | 2026-11-16 |
| ruff | alpha | Linting and formatting. | 2026-11-16 |
| types-pyyaml | alpha | Type stubs for pyyaml, so strict pyright checks the tests that use it. | 2026-11-16 |
