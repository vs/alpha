# Security

## Secrets

Nothing is deployed.

Locally, secrets live in `.env` files, which git ignores; never commit them. Claude can't edit them, and the Stop hook blocks a change that adds a secret to the repository.

## Auth

none

## Protected paths

Claude can't edit these. Lockfiles change only through the package manager; change the others by hand.

- `**/.env`
- `**/.env.*`
- `**/*.pem`
- `**/*.key`
- `uv.lock`
