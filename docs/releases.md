# Releases

Semantic versioning (MAJOR.MINOR.PATCH): a breaking change bumps MAJOR, a new feature MINOR, a fix PATCH.

One version for the whole repository.

Changes are written up in the GitHub release notes for each version.

## Cutting a release

Bump the version in .claude-plugin/plugin.json, pyproject.toml and src/alpha/__init__.py (plus uv.lock) in a chore: Release X.Y.Z commit on main, tag vX.Y.Z and publish a GitHub release with its notes. Users get it with claude plugin marketplace update alpha.
