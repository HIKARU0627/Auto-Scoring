# auto-scoring-backend

Python sidecar for Auto-Scoring: FastAPI over a framework-free domain core.

- Toolchain: Python 3.12+ ([`.python-version`](./.python-version)) managed with
  [uv](https://docs.astral.sh/uv/); dependencies locked in [`uv.lock`](./uv.lock).
- Layers (dependency direction `api → adapters → db ← domain`, enforced by
  `tests/test_architecture.py`):
  - `src/auto_scoring/domain/` — MVP entities, invariants, and repository
    ports. No FastAPI, SQLAlchemy, HTTP clients, or external SDKs.
  - `src/auto_scoring/db/` — SQLAlchemy 2 ORM tables, the WAL-mode SQLite
    engine, and the Alembic migrator (`backend/migrations/`). May depend on
    `domain`, never on `adapters` / `api`.
  - `src/auto_scoring/adapters/` — concrete implementations of the domain
    ports: SQLAlchemy repositories + Unit of Work, local file storage
    (`app-data/`, atomic writes), and bulk delete.
  - `src/auto_scoring/api/` — thin FastAPI routers (`create_app()` in `api/app.py`).
- The MVP data model and `app-data/` storage rules are documented in
  [`../docs/data-model-and-local-storage.md`](../docs/data-model-and-local-storage.md).

Restore and run the gates from the repo root: `uv sync --locked` (or
`pnpm run bootstrap`), then `pnpm run lint:backend`, `pnpm run typecheck:backend`,
`pnpm run test:backend`. Apply migrations with
`AUTO_SCORING_DB_URL=sqlite:///app-data/database.sqlite uv run alembic upgrade head`
or, from Python, `auto_scoring.db.migrator.upgrade(url)`.
