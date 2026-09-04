"""Migrations against a real SQLite file: fresh DB, one-generation-old DB, downgrade."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from alembic import command
from pypdf import PdfWriter
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine
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

    assert _CORE_TABLES | {"operation_log", "answer_images"} <= _tables(db_url)
    assert current_revision(db_url) == "0003"


def test_one_generation_old_database_upgrades_to_head(db_url: str) -> None:
    # A database created before 0002 existed.
    upgrade(db_url, "0001")
    assert "operation_log" not in _tables(db_url)

    upgrade(db_url, "head")
    assert "operation_log" in _tables(db_url)
    assert "answer_images" in _tables(db_url)
    assert current_revision(db_url) == "0003"


def test_two_generations_old_database_upgrades_to_head(db_url: str) -> None:
    # A database created before 0003 existed.
    upgrade(db_url, "0002")
    assert "answer_images" not in _tables(db_url)

    upgrade(db_url, "head")
    assert "answer_images" in _tables(db_url)
    assert current_revision(db_url) == "0003"


def _pdf_bytes(*, pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=300, height=400)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_backfills_pre_existing_submission_metadata_on_upgrade(db_url: str, db_path: Path) -> None:
    """A submission row from before 0003 gets a real sha256/page_count backfilled
    from its still-present source.pdf, instead of the column defaults ("" / 1)
    that would otherwise make it fail to load (Submission.__post_init__ rejects
    an empty source_pdf_sha256).
    """
    upgrade(db_url, "0002")
    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as conn:
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
                    "VALUES ('with-file', 't', 'submissions/with-file/source.pdf', "
                    "'unprocessed', '2026-01-01')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO submissions "
                    "(id, test_id, source_pdf_path, state, created_at) "
                    "VALUES ('missing-file', 't', 'submissions/missing-file/source.pdf', "
                    "'unprocessed', '2026-01-01')"
                )
            )
            conn.commit()
    finally:
        engine.dispose()

    pdf_bytes = _pdf_bytes(pages=2)
    pdf_path = db_path.parent / "submissions" / "with-file" / "source.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_bytes)
    # "missing-file"'s source.pdf is deliberately never written (already purged,
    # or a hand-built fixture) to exercise the fallback path.

    upgrade(db_url, "head")

    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as conn:
            rows = {
                row.id: row
                for row in conn.execute(
                    text("SELECT id, source_pdf_sha256, page_count FROM submissions ORDER BY id")
                )
            }
    finally:
        engine.dispose()

    with_file = rows["with-file"]
    assert with_file.source_pdf_sha256 == hashlib.sha256(pdf_bytes).hexdigest()
    assert with_file.page_count == 2

    missing_file = rows["missing-file"]
    assert missing_file.source_pdf_sha256  # non-empty: Submission.__post_init__ needs it
    assert missing_file.source_pdf_sha256 != "0" * 64
    assert missing_file.page_count == 1

    # And the backfilled rows actually load through the domain layer.
    session_factory = build_session_factory(create_sqlite_engine(db_url))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        loaded = {s.id: s for s in uow.submissions.list_for_test("t")}
    assert loaded["with-file"].source_pdf_sha256 == with_file.source_pdf_sha256
    assert loaded["missing-file"].page_count == 1


def test_downgrade_walks_back_to_base(db_url: str) -> None:
    upgrade(db_url, "head")

    downgrade(db_url, "0002")
    assert "answer_images" not in _tables(db_url)
    assert _tables(db_url) >= _CORE_TABLES

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

        bad_submission = text(
            "INSERT INTO submissions "
            "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, created_at) "
            "VALUES ('s', 't', 'submissions/s/source.pdf', '" + ("0" * 64) + "', 0, "
            "'unprocessed', '2026-01-01')"  # page_count 0 violates the positive-page-count check
        )
        with pytest.raises(IntegrityError):
            conn.execute(bad_submission)
    finally:
        conn.close()
        engine.dispose()


@pytest.mark.parametrize(
    "status,reason",
    [
        pytest.param("ok", "'should be null'", id="ok-with-reason"),
        pytest.param("needs_review", "NULL", id="needs_review-without-reason"),
        pytest.param("needs_review", "''", id="needs_review-with-empty-reason"),
    ],
)
def test_answer_image_check_constraint_rejects_reason_status_mismatch(
    db_url: str, status: str, reason: str
) -> None:
    """domain.models.AnswerImage.__post_init__'s reason/status invariant is also
    enforced by the DB, so a row written outside the app layer (or a future bug
    in it) can't slip an inconsistent row past every check and only blow up as a
    DomainError later, at read time (AGENTS.md "invariant … with real
    constraints").
    """
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
                "INSERT INTO questions (id, test_id, number, page, points, scoring_method) "
                "VALUES ('q', 't', '1', 1, 5, 'additive')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO submissions "
                "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, "
                "state, created_at) "
                "VALUES ('s', 't', 'submissions/s/source.pdf', '" + ("3" * 64) + "', 1, "
                "'unprocessed', '2026-01-01')"
            )
        )
        conn.commit()

        bad_answer_image = text(
            "INSERT INTO answer_images "
            "(id, submission_id, question_id, page, image_path, status, reason, created_at) "
            f"VALUES ('ai', 's', 'q', 1, 'submissions/s/pages/page-1.png', "
            f"'{status}', {reason}, '2026-01-01')"
        )
        with pytest.raises(IntegrityError):
            conn.execute(bad_answer_image)
    finally:
        conn.close()
        engine.dispose()


@pytest.mark.parametrize(
    "bad_insert",
    [
        "INSERT INTO submissions "
        "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, created_at) "
        "VALUES ('bad-sub', 't', 'submissions/bad-sub/source.pdf', '" + ("1" * 64) + "', 1, "
        "'unknown', '2026-01-01')",
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
                "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, created_at) "
                "VALUES ('sub', 't', 'submissions/sub/source.pdf', '" + ("2" * 64) + "', 1, "
                "'unprocessed', '2026-01-01')"
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
    assert {
        "0001_initial_schema.py",
        "0002_operation_log.py",
        "0003_answer_intake.py",
    } <= names
