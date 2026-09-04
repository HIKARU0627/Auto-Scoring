# auto_scoring_app

Flutter desktop front-end for Auto-Scoring (Windows, Material 3).

- Toolchain: Flutter 3.41.4 stable / Dart 3 — pinned in [`.fvmrc`](./.fvmrc).
- Layers (dependency direction `features → core → api`, enforced by
  `test/architecture_test.dart`):
  - `lib/api/` — backend (Python sidecar) client. Generated from the OpenAPI
    schema in a later issue; currently a stub.
  - `lib/core/` — Material 3 theme and the dependency container.
  - `lib/features/` — screens and their state.

Run the gates from the repo root: `pnpm run lint:app`, `pnpm run test:app`,
`pnpm run build:app`. See [`../docs/quality-gates.md`](../docs/quality-gates.md).
