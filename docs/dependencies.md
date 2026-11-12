# Dependencies

## Policy

- Adding: every new dependency gets a row in the log below, with the reason. The Stop hook blocks a lockfile change without one.
- Pinning: lockfiles pin every version. Only the package manager changes them; Claude can't edit them by hand.
- Upgrading: Upgrades are manual: check for updates weekly.

## Log

Log every dependency added, with the reason.

| Dependency | Component | Why | Added |
|---|---|---|---|
