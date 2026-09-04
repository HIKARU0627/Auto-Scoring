"""Migrations against a real SQLite file: fresh DB, one-generation-old DB, downgrade."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from auto_scoring.db.engine import create_sqlite_engine
from auto_scoring.db.migrator import alembic_config, current_revision, downgrade, upgrade

_CORE_TABLES = {
    "tests",
    "questions",
    "rubrics",
    "rubric_criteria",
    "submissions",
    "recognition_results",
    "grade_results",
    "annotations",
    "reviews",
    "jobs",
}


def _tables(db_url: str) -> set[str]:
    engine = create_sqlite_engine(db_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_fresh_database_upgrades_to_head(db_url: str) -> None:
    upgrade(db_url, "head")

    assert _CORE_TABLES | {"operation_log"} <= _tables(db_url)
    assert current_revision(db_url) == "0002"


def test_one_generation_old_database_upgrades_to_head(db_url: str) -> None:
    # A database created before 0002 existed.
    upgrade(db_url, "0001")
    assert "operation_log" not in _tables(db_url)

    upgrade(db_url, "head")
    assert "operation_log" in _tables(db_url)
    assert current_revision(db_url) == "0002"


def test_downgrade_walks_back_to_base(db_url: str) -> None:
    upgrade(db_url, "head")

    downgrade(db_url, "0001")
    assert "operation_log" not in _tables(db_url)
    assert _tables(db_url) >= _CORE_TABLES

    downgrade(db_url, "base")
    assert _CORE_TABLES.isdisjoint(_tables(db_url))


def test_head_schema_matches_orm_metadata(db_url: str) -> None:
    """`alembic check` finds no difference between the migrations and the ORM."""
    upgrade(db_url, "head")
    command.check(alembic_config(db_url))  # raises if a model change is unmigrated


def test_connection_enforces_wal_and_foreign_keys(db_url: str) -> None:
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
    finally:
        engine.dispose()


def test_check_constraint_rejects_bad_row(db_url: str) -> None:
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, created_at) "
                "VALUES ('t', 'n', 'additive', '2026-01-01')"
            )
        )
        conn.commit()
        bad_question = text(
            "INSERT INTO questions "
            "(id, test_id, number, page, points, scoring_method) "
            "VALUES ('q', 't', '1', 0, 5, 'additive')"  # page 0 violates ck_questions_page_positive
        )
        with pytest.raises(IntegrityError):
            conn.execute(bad_question)
    finally:
        conn.close()
        engine.dispose()


@pytest.mark.parametrize(
    "bad_insert",
    [
        "INSERT INTO submissions "
        "(id, test_id, source_pdf_path, state, created_at) "
        "VALUES ('bad-sub', 't', 'submissions/bad-sub/source.pdf', 'unknown', '2026-01-01')",
        "INSERT INTO jobs "
        "(id, kind, submission_id, state, attempts, max_attempts, created_at, updated_at) "
        "VALUES ('job', 'grading', 'sub', 'unknown', 0, 3, '2026-01-01', '2026-01-01')",
    ],
)
def test_state_check_constraints_reject_unknown_values(db_url: str, bad_insert: str) -> None:
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, created_at) "
                "VALUES ('t', 'n', 'additive', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO submissions "
                "(id, test_id, source_pdf_path, state, created_at) "
                "VALUES ('sub', 't', 'submissions/sub/source.pdf', 'unprocessed', '2026-01-01')"
            )
        )
        conn.commit()

        with pytest.raises(IntegrityError):
            conn.execute(text(bad_insert))
    finally:
        conn.close()
        engine.dispose()


def test_migration_file_paths_exist() -> None:
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    names = {p.name for p in versions.glob("*.py")}
    assert {"0001_initial_schema.py", "0002_operation_log.py"} <= names
