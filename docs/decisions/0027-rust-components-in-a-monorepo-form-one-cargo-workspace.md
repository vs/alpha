# 0027. Rust components in a monorepo form one Cargo workspace

Date: 2026-11-14
Status: accepted
Kind: technical

## Context

The user asked: "make alpha's Rust defaults: workspace, branch coverage, mutation testing". This record is the first of the three. Their brief for it: a monorepo's Rust components form one Cargo workspace whose root `Cargo.toml` has no `[package]`, with the lints and every dependency version declared once at the root; the commands keep working from each component's folder; `layout = "single"` keeps the single-crate files; the default is on and the interview can override it.

Until now the Rust recipe made every component a crate of its own, each with its `Cargo.lock`, `rust-toolchain.toml`, `clippy.toml` and `target/`. Two components that share code then pin the same dependency twice and build it twice.

The rest is Claude's choice, open to correction:

- Where the layout is described. The recipe gets a `[workspace]` table (root files, member files, root and member ignores, rules that replace the recipe's for a member), so the generator stays stack-neutral. Only a kit recipe may have one; a drafted recipe with a workspace is refused.
- How it is switched. `defaults.components.workspace` (true), and the components answer `"workspace": false` for separate crates. A component at `"."` is never a member, since a workspace root with a package can't also be the virtual root.
- A sibling dependency. The user's brief writes it in the member as `foo = { path = "../foo" }`, "declared in the workspace too". Claude read that as: the sibling is a member of the workspace, and the path stays in the member; alpha generates no dependency between components.
- What the commands needed. Run on real tools (Rust 1.99.1, cargo-machete 0.9.2) in a member that depends on a sibling: `cargo test`, `cargo fmt --check`, `cargo check` and `cargo machete` cover only that member. `cargo clippy` also lints the sibling, and `-p <package>` doesn't stop it; `--no-deps` does, so the recipe's lint command gains it for both layouts.

## Decision

In a monorepo, the components of a stack whose recipe has a `[workspace]` are its members, unless `workspace` is false in the answers (default: `defaults.components.workspace`, true). For Rust:

- The root gets `Cargo.toml` (`[workspace]` with the members' folders and `resolver = "3"`, `[workspace.package]`, an empty `[workspace.dependencies]`, and the lint block as `[workspace.lints.rust]` and `[workspace.lints.clippy]`), `clippy.toml` and `rust-toolchain.toml`. Cargo writes one `Cargo.lock` and one `target/` there.
- A member gets a `Cargo.toml` that inherits `version`, `edition`, `publish` and `[lints]` from the workspace, and a `tests/setup.rs` that checks the root manifest's lints and its own `[lints] workspace = true`.
- `docs/principles.toml` lists the root `Cargo.lock` as each member's lockfile, the root `Cargo.toml` among its manifests, and the root files under `workspace`. The hooks treat a file a component lists this way as that component's too: a change to the root manifest runs every member's checks, and a lockfile change asks for one dependency log entry.
- `.gitignore`, the tool configs, lockfile protection, the vulns check, Dependabot (one `cargo` entry at `/`) and CI (`rust-src-dir` and `cache-workspaces` at the root) point at the root files. The root ignores are anchored (`/target/`), so a folder named `target` in a Python or TypeScript component is still tracked and checked.
- The `cargo-for-dependencies` rule reads, for a member: "Declare each dependency once, in `[workspace.dependencies]` of the root Cargo.toml, and name it in a member with `foo.workspace = true`; add and remove them with cargo commands where cargo supports it, never by copying versions into a member."
- The skeleton commit holds the root files and every member together, since they pass their checks only together.

`layout = "single"` and a project that answers `"workspace": false` keep the single-crate files.

## Consequences

- `alpha update` moves an existing Rust monorepo to the workspace: new root files, each member's `Cargo.toml` and `tests/setup.rs` merged, the members' `clippy.toml` and `rust-toolchain.toml` reported as stale, and a note for each member's `Cargo.lock` to delete (with its `target/`). Dependencies a member already declares stay in its `Cargo.toml` until someone moves their versions to the root. A project that wants to stay as it is sets `"workspace": false` first.
- A dependency listed in `[workspace.dependencies]` that no member names isn't reported: cargo-machete reads only the members.
- Python and TypeScript components are untouched: Cargo reads only the members it lists, and `rust-toolchain.toml` matters only to cargo.
- An adopted repo keeps its own layout; adopted recipes have no workspace.
- Not verified: the workflow on GitHub (the cache keyed on the root).
