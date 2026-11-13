# Dependencies

## Policy

- Adding: every new dependency gets a row in the log below, with the reason. The Stop hook blocks a lockfile change without one; a release that only bumps the project's own version in uv.lock or Cargo.lock needs none.
- Pinning: lockfiles pin every version. Only the package manager changes them; Claude can't edit them by hand.
- Upgrading: Upgrades are manual: check for updates weekly.

## Log

Log every dependency added, with the reason.

| Dependency | Component | Why | Added |
|---|---|---|---|
| deptry (dev) | alpha | The structure check: finds unused, missing and transitive dependencies, as alpha's Python recipe does | 2026-11-12 |
| pytest-cov (dev) | alpha | Writes the coverage report the recipe's coverage command reads, as alpha's Python recipe does | 2026-11-12 |
