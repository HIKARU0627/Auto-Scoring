# Quality gates

Local commands and GitHub Actions run the same checks. Each check is a `scripts`
entry in `package.json`, invoked as `pnpm run <script>`.

| Gate               | Command                 | CI step (`.github/workflows/ci.yml`) |
| ------------------ | ----------------------- | ------------------------------------ |
| Agent skill mirror | `pnpm run skills:check` | Check agent skill mirrors            |
| Formatting         | `pnpm run format:check` | Check formatting                     |
| Lint               | `pnpm run lint`         | Lint                                 |
| Typecheck          | `pnpm run typecheck`    | Typecheck                            |
| Test               | `pnpm run test`         | Test                                 |
| Build              | `pnpm run build`        | Build                                |
| Everything         | `pnpm run check`        | (all of the above)                   |

`lint` / `typecheck` / `test` / `build` ship as no-ops that print
`not configured`. Replace those scripts for your project — see
`TEMPLATE_SETUP.md`.

## git hooks vs CI

- `.githooks/pre-commit` runs `pnpm run check:pre-commit` (skill mirror +
  formatting): fast, deterministic, non-destructive.
- `.githooks/pre-push` runs `pnpm run check:pre-push` (lint + typecheck + test).
- Hooks can be bypassed with `--no-verify`, so GitHub Actions runs the full set
  as a merge gate. Make the real checks required in the branch ruleset.
- `pnpm run bootstrap` points the current worktree at `.githooks/`
  (`git config core.hooksPath .githooks`).

## Adding heavier gates

Add integration / e2e / contract jobs directly to `.github/workflows/ci.yml` as
separate jobs, and add matching `package.json` scripts. Keep hook-run checks
fast; put anything slow or environment-heavy in CI only.

## Where the gate list lives

The gate list is defined in two places that must stay in step:

- `package.json` — the `check`, `check:pre-commit`, `check:pre-push` scripts.
- `.github/workflows/ci.yml` — one step per gate (split out so a failure names
  itself in the CI UI).

When you add or remove a gate, update both, and this table.

## Toolchain

Node version is pinned in `.node-version`; the package manager is pinned in
`package.json` `packageManager`. CI reads the same files. Use
`pnpm install --frozen-lockfile`.

Non-Node project: point the `lint` / `typecheck` / `test` / `build` scripts at
your own tools (e.g. `"test": "cargo test"`) — `package.json` then acts purely as
a task runner. Keep `skills:sync` and `format` on Node (template infrastructure).
Adjust `.github/workflows/ci.yml` to install your toolchain.
