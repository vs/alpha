# Dependencies

## Policy

- Adding: every new dependency gets a row in the log below, with the reason. The Stop hook blocks a lockfile change without one; a release that only bumps the project's own version in uv.lock or Cargo.lock needs none.
- Pinning: lockfiles pin every version. Only the package manager changes them; Claude can't edit them by hand.
- Upgrading: Dependabot opens weekly update pull requests, per component and for the CI actions.

## Log

Log every dependency added, with the reason.

| Dependency | Component | Why | Added |
|---|---|---|---|
