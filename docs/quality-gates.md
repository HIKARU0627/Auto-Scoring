# Quality gates

Local commands and GitHub Actions run the same checks. Each check is a `scripts`
entry in `package.json`, invoked as `pnpm run <script>`.

| Gate               | Command                  | CI step (`.github/workflows/ci.yml`) |
| ------------------ | ------------------------ | ------------------------------------ |
| Agent skill mirror | `pnpm run skills:check`  | Check agent skill mirrors            |
| Formatting         | `pnpm run format:check`  | Check formatting                     |
| OpenAPI contract   | `pnpm run openapi:check` | OpenAPI contract                     |
| Lint               | `pnpm run lint`          | Lint                                 |
| Typecheck          | `pnpm run typecheck`     | Typecheck                            |
| Test               | `pnpm run test`          | Test                                 |
| Build              | `pnpm run build`         | Build                                |
| Everything         | `pnpm run check`         | (all of the above)                   |

`openapi:check` regenerates `backend/openapi/openapi.json` and the Dart client
in `app/packages/auto_scoring_api/` and fails on any git diff. It needs `uv`,
`dart`, and Java (openapi-generator) on PATH, so it stays out of the git hooks
(`check:pre-commit` / `check:pre-push`) and runs only in `pnpm run check` and CI.
See [`sidecar-api.md`](./sidecar-api.md) §4.

`package.json` is a task runner over the two stacks. Each gate fans out to an
`:app` (Flutter) and a `:backend` (Python) script:

| Gate        | `:app`                                                  | `:backend`                           |
| ----------- | ------------------------------------------------------- | ------------------------------------ |
| `lint`      | `dart format --set-exit-if-changed` + `flutter analyze` | `ruff check` + `ruff format --check` |
| `typecheck` | `flutter analyze`                                       | `mypy` (`strict`)                    |
| `test`      | `flutter test`                                          | `pytest`                             |
| `build`     | `flutter build windows --debug`                         | `python -c "import auto_scoring"`    |

`format` / `format:check` stay on Prettier for the repo-level files; `app/` and
`backend/` are in `.prettierignore` because Dart and Ruff own their formatting.

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

| Tool    | Pin                                                       | Restored by                                    |
| ------- | --------------------------------------------------------- | ---------------------------------------------- |
| Node    | `.node-version`                                           | `pnpm install --frozen-lockfile`               |
| pnpm    | `package.json` `packageManager`                           | Corepack                                       |
| Flutter | `app/.fvmrc` (3.41.4 stable) + `.github/workflows/ci.yml` | `flutter pub get` (uses `app/pubspec.lock`)    |
| Python  | `backend/.python-version` (3.12)                          | `uv sync --locked` (downloads the interpreter) |
| uv      | `.github/workflows/ci.yml` (`setup-uv` version)           | —                                              |

`pnpm run bootstrap` restores all four in one step. CI (`.github/workflows/ci.yml`)
runs on `windows-latest` so the Flutter Windows debug build is exercised as a
merge gate; it installs the Flutter SDK (`subosito/flutter-action`) and `uv`
(`astral-sh/setup-uv`) before the gates.
