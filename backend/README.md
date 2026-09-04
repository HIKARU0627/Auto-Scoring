# auto-scoring-backend

Python sidecar for Auto-Scoring: FastAPI over a framework-free domain core.

- Toolchain: Python 3.12+ ([`.python-version`](./.python-version)) managed with
  [uv](https://docs.astral.sh/uv/); dependencies locked in [`uv.lock`](./uv.lock).
- Layers (dependency direction `api → domain ← adapters`, enforced by
  `tests/test_architecture.py`):
  - `src/auto_scoring/domain/` — scoring rules and ports. No FastAPI,
    SQLAlchemy, HTTP clients, or external SDKs.
  - `src/auto_scoring/adapters/` — concrete implementations of the domain ports.
  - `src/auto_scoring/api/` — thin FastAPI routers (`create_app()` in `api/app.py`).

Restore and run the gates from the repo root: `uv sync --locked` (or
`pnpm run bootstrap`), then `pnpm run lint:backend`, `pnpm run typecheck:backend`,
`pnpm run test:backend`.
