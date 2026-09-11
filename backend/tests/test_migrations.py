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
    assert current_revision(db_url) == "0021"


def test_programmatic_upgrade_ignores_a_stray_auto_scoring_db_url(
    db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``migrations/env.py`` used to check ``AUTO_SCORING_DB_URL`` before the
    ``db_url`` this call was explicitly given, so a value inherited by the
    process environment (e.g. left over from a developer's shell, or set by
    whatever launched the sidecar) would silently redirect a programmatic
    `upgrade()` to a completely different database -- the sidecar's startup
    migration would then migrate that unrelated DB while going on to open
    and serve requests against the (possibly still unmigrated)
    ``--app-data-dir`` database (Issue #26 review). `upgrade(db_url, ...)`
    must always target exactly the `db_url` it was given, never the env var.
    """
    decoy_path = tmp_path / "decoy.sqlite"
    monkeypatch.setenv("AUTO_SCORING_DB_URL", f"sqlite:///{decoy_path}")

    upgrade(db_url, "head")

    assert current_revision(db_url) == "0021"
    assert not decoy_path.exists()


def test_one_generation_old_database_upgrades_to_head(db_url: str) -> None:
    # A database created before 0002 existed.
    upgrade(db_url, "0001")
    assert "operation_log" not in _tables(db_url)

    upgrade(db_url, "head")
    assert "operation_log" in _tables(db_url)
    assert "answer_images" in _tables(db_url)
    assert current_revision(db_url) == "0021"


def test_two_generations_old_database_upgrades_to_head(db_url: str) -> None:
    # A database created before 0005 (answer_intake) existed.
    upgrade(db_url, "0002")
    assert "answer_images" not in _tables(db_url)

    upgrade(db_url, "head")
    assert "answer_images" in _tables(db_url)
    assert current_revision(db_url) == "0021"


def _pdf_bytes(*, pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=300, height=400)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_backfills_pre_existing_submission_metadata_on_upgrade(db_url: str, db_path: Path) -> None:
    """A submission row from before 0005 gets a real sha256/page_count backfilled
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


def test_backfills_pre_existing_tests_as_ready_on_upgrade(db_url: str) -> None:
    """A `Test` row from before 0011 (``status`` didn't exist, and neither
    did the two-PDF registration flow it gates) must come out the other
    side ``ready``, not ``draft``.

    Before 0011, answer intake accepted a submission for any test
    unconditionally; afterward, ``GET /tests`` and ``intake_submission``
    both reject anything short of ``ready``. Such a row never had -- and,
    lacking registration PDFs, can never retroactively earn -- a profile or
    dependency graph to confirm, so backfilling it to ``draft`` would make
    it permanently unusable for new submissions with no way to recover
    (Issue #16 review round 6).
    """
    upgrade(db_url, "0007")
    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO tests (id, name, default_scoring_method, created_at) "
                    "VALUES ('legacy-test', 'n', 'additive', '2026-01-01')"
                )
            )
            conn.commit()
    finally:
        engine.dispose()

    upgrade(db_url, "head")

    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as conn:
            status = conn.execute(
                text("SELECT status FROM tests WHERE id = 'legacy-test'")
            ).scalar_one()
    finally:
        engine.dispose()
    assert status == "ready"

    session_factory = build_session_factory(create_sqlite_engine(db_url))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        loaded = uow.tests.get("legacy-test")
    assert loaded is not None
    assert loaded.status.value == "ready"


def test_legacy_duplicate_content_is_rejected_before_any_ddl_and_retry_recovers(
    db_url: str, db_path: Path
) -> None:
    """Two pre-0005 submissions in the same test with byte-identical PDFs
    would violate the new uq_submissions_test_content_hash constraint. The
    preflight check must raise before either batch pass touches
    ``submissions`` -- leaving the DB exactly at revision 0004 (the last
    revision to apply cleanly before 0005 raises), with no new column and no
    leftover ``_alembic_tmp_submissions`` -- so that purging the duplicate
    and re-running ``upgrade`` is a clean retry, not a second failure
    (0005's docstring: "resolve by hand ... and re-run the upgrade").
    """
    upgrade(db_url, "0002")
    pdf_bytes = _pdf_bytes(pages=1)
    for submission_id in ("dup-1", "dup-2"):
        pdf_path = db_path.parent / "submissions" / submission_id / "source.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)

    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO tests (id, name, default_scoring_method, created_at) "
                    "VALUES ('t', 'n', 'additive', '2026-01-01')"
                )
            )
            for submission_id in ("dup-1", "dup-2"):
                conn.execute(
                    text(
                        "INSERT INTO submissions "
                        "(id, test_id, source_pdf_path, state, created_at) "
                        "VALUES (:id, 't', :path, 'unprocessed', '2026-01-01')"
                    ),
                    {"id": submission_id, "path": f"submissions/{submission_id}/source.pdf"},
                )
            conn.commit()
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="uq_submissions_test_content_hash"):
        upgrade(db_url, "head")

    # Untouched: still 0004, no new column, no leftover batch-mode temp table.
    assert current_revision(db_url) == "0004"
    engine = create_sqlite_engine(db_url)
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("submissions")}
        assert "source_pdf_sha256" not in columns
        assert "_alembic_tmp_submissions" not in _tables(db_url)
    finally:
        engine.dispose()

    # Resolve by hand: purge one of the two duplicates.
    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM submissions WHERE id = 'dup-2'"))
            conn.commit()
    finally:
        engine.dispose()

    upgrade(db_url, "head")
    assert current_revision(db_url) == "0021"


_CHILD_TABLES = (
    "recognition_results",
    "grade_results",
    "annotations",
    "reviews",
    "jobs",
)


def test_upgrade_preserves_child_rows_of_a_recreated_submissions_table(db_url: str) -> None:
    """SQLite performs an implicit ``DELETE FROM`` -- cascading to any ``ON
    DELETE CASCADE`` children -- when a table is ``DROP``ped while foreign key
    enforcement is on. Alembic's SQLite batch mode (used here because SQLite
    can't add a ``CHECK``/``UNIQUE`` constraint without recreating the table)
    does exactly that to ``submissions`` internally. Every table with a FK to
    ``submissions.id ON DELETE CASCADE`` must still have its rows after the
    upgrade, not silently lose them (migrations/env.py disables foreign key
    enforcement for the whole migration run to prevent this).
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
                    "INSERT INTO questions (id, test_id, number, page, points, scoring_method) "
                    "VALUES ('q', 't', '1', 1, 5, 'additive')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO submissions "
                    "(id, test_id, source_pdf_path, state, created_at) "
                    "VALUES ('s', 't', 'submissions/s/source.pdf', 'unprocessed', '2026-01-01')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO recognition_results "
                    "(id, submission_id, question_id, source, text, confidence, boxes, "
                    "created_at) "
                    "VALUES ('r1', 's', 'q', 'ai', 'x', 0.9, '[]', '2026-01-01')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO grade_results "
                    "(id, submission_id, question_id, source, awarded, maximum, confidence, "
                    "criteria, created_at) "
                    "VALUES ('g1', 's', 'q', 'ai', 3, 5, 0.8, '[]', '2026-01-01')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO annotations "
                    "(id, submission_id, question_id, source, kind, created_at) "
                    "VALUES ('a1', 's', 'q', 'ai', 'comment', '2026-01-01')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO reviews "
                    "(id, submission_id, question_id, action, ai_grade_result_id, created_at) "
                    "VALUES ('rv1', 's', 'q', 'approved', 'g1', '2026-01-01')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO jobs "
                    "(id, kind, submission_id, state, attempts, max_attempts, created_at, "
                    "updated_at) "
                    "VALUES ('j1', 'grading', 's', 'queued', 0, 3, '2026-01-01', '2026-01-01')"
                )
            )
            conn.commit()
    finally:
        engine.dispose()

    upgrade(db_url, "head")

    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM submissions")).scalar() == 1
            for table in _CHILD_TABLES:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                assert count == 1, f"{table} lost its row(s) during the submissions recreate"
    finally:
        engine.dispose()


def test_reintake_key_is_unique_per_test(db_url: str) -> None:
    """A second submission with the same (test_id, source_pdf_sha256) is
    rejected by the DB itself, not just by the application's pre-insert
    lookup -- closing the race window between two concurrent intake requests
    checking "does this hash already exist" at the same time.
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO submissions "
                "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, "
                "state, created_at) "
                "VALUES ('s1', 't', 'submissions/s1/source.pdf', '" + ("4" * 64) + "', 1, "
                "'unprocessed', '2026-01-01')"
            )
        )
        conn.commit()

        duplicate = text(
            "INSERT INTO submissions "
            "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, created_at) "
            "VALUES ('s2', 't', 'submissions/s2/source.pdf', '" + ("4" * 64) + "', 1, "
            "'unprocessed', '2026-01-01')"
        )
        with pytest.raises(IntegrityError):
            conn.execute(duplicate)
    finally:
        conn.close()
        engine.dispose()


def test_submission_metadata_columns_require_a_value_after_upgrade(db_url: str) -> None:
    """The temporary migration-time defaults ("" / 1) that let ``ADD COLUMN``
    succeed against pre-existing rows are removed once every row has a real
    value (see 0005's docstring); an insert that omits them must fail loudly
    instead of silently getting an empty hash or a fabricated page count.
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.commit()

        missing_metadata = text(
            "INSERT INTO submissions (id, test_id, source_pdf_path, state, created_at) "
            "VALUES ('s', 't', 'submissions/s/source.pdf', 'unprocessed', '2026-01-01')"
        )
        with pytest.raises(IntegrityError):
            conn.execute(missing_metadata)
    finally:
        conn.close()
        engine.dispose()


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


def test_downgrade_from_0009_normalizes_a_failed_usable_row(db_url: str) -> None:
    """Issue #18 review round 3, P2: a FAILED job's `usable` bit (settable
    only once 0009's upgrade has run, via a human /resume approval) has no
    representation in 0008's stricter constraint. Batch mode's "recreate"
    copies every existing row when dropping/recreating the constraint;
    downgrading with such a row present must normalize it away first, not
    abort partway through with an IntegrityError.
    """
    upgrade(db_url, "0009")
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
                    "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, "
                    "created_at) VALUES ('s', 't', 'p', :sha, 1, 'unprocessed', '2026-01-01')"
                ),
                {"sha": "0" * 64},
            )
            conn.execute(
                text(
                    "INSERT INTO jobs (id, kind, submission_id, state, attempts, max_attempts, "
                    "usable, created_at, updated_at) VALUES "
                    "('j', 'grading', 's', 'failed', 1, 3, 1, '2026-01-01', '2026-01-01')"
                )
            )
            conn.commit()
    finally:
        engine.dispose()

    downgrade(db_url, "0008")  # must not raise IntegrityError

    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT usable FROM jobs WHERE id = 'j'")).one()
    finally:
        engine.dispose()
    assert row.usable is None


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
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
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

        overlong_label_submission = text(
            "INSERT INTO submissions "
            "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, "
            "student_label, created_at) "
            "VALUES ('s2', 't', 'submissions/s2/source.pdf', '" + ("1" * 64) + "', 1, "
            "'unprocessed', '" + ("a" * 201) + "', '2026-01-01')"
        )
        with pytest.raises(IntegrityError):
            conn.execute(overlong_label_submission)

        overlong_filename_submission = text(
            "INSERT INTO submissions "
            "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, "
            "original_filename, created_at) "
            "VALUES ('s3', 't', 'submissions/s3/source.pdf', '" + ("2" * 64) + "', 1, "
            "'unprocessed', '" + ("a" * 256) + "', '2026-01-01')"
        )
        with pytest.raises(IntegrityError):
            conn.execute(overlong_filename_submission)

        conn.execute(
            text(
                "INSERT INTO questions (id, test_id, number, page, points, scoring_method) "
                "VALUES ('q', 't', '1', 1, 5, 'additive')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO submissions "
                "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, "
                "created_at) "
                "VALUES ('s-text-len', 't', 'submissions/s-text-len/source.pdf', '"
                + ("9" * 64)
                + "', 1, 'unprocessed', '2026-01-01')"
            )
        )
        conn.commit()
        overlong_recognition_text = text(
            "INSERT INTO recognition_results "
            "(id, submission_id, question_id, source, text, confidence, boxes, created_at) "
            "VALUES ('r-overlong', 's-text-len', 'q', 'ai', '" + ("a" * 10_001) + "', 0.5, '[]', "
            "'2026-01-01')"
        )
        with pytest.raises(IntegrityError):
            conn.execute(overlong_recognition_text)
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
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
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
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
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


def test_a_grade_cannot_be_stored_for_an_image_that_is_not_the_answer(db_url: str) -> None:
    """DB-level mirror of `GradeResult.__post_init__` (Issue #136, migration
    0017).

    A grade row produced from a crop the grading AI itself said is not this
    question's answer is the defect this Issue removes: on screen it reads
    "0 / 20 点・採点信頼度 100%", exactly like a correct 0. The pipeline
    never writes one -- and a later code path must not be able to either,
    which is what makes this a database rule rather than only a validation
    (AGENTS.md "Architecture").

    Enforced by a trigger rather than a CHECK constraint, and asserted here
    through both the INSERT and the UPDATE path because a trigger, unlike a
    CHECK, only covers the statements it names. Why a trigger at all is in
    migration 0017's docstring: a CHECK would mean rebuilding
    ``grade_results``, which reorders how SQLite applies cascades and breaks
    deleting a test.

    ``blank`` is stored, because a question a student genuinely left empty
    is an ordinary answer sheet and its 0 may well be right; how often that
    happens is the number that decides whether it should stop a grade too.
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
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
                "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, created_at) "
                "VALUES ('s', 't', 'submissions/s/source.pdf', '" + ("4" * 64) + "', 1, "
                "'unprocessed', '2026-01-01')"
            )
        )
        conn.commit()

        def _insert_grade(row_id: str, finding: str) -> None:
            conn.execute(
                text(
                    "INSERT INTO grade_results "
                    "(id, submission_id, question_id, source, awarded, maximum, "
                    "confidence, criteria, context, answer_image_finding, created_at) "
                    f"VALUES ('{row_id}', 's', 'q', 'ai', 0, 5, 1.0, '[]', '[]', "
                    f"'{finding}', '2026-01-01')"
                )
            )

        with pytest.raises(IntegrityError):
            _insert_grade("g-not-the-answer", "not_the_answer")
        conn.rollback()

        with pytest.raises(IntegrityError):
            _insert_grade("g-nonsense", "probably")
        conn.rollback()

        _insert_grade("g-blank", "blank")
        _insert_grade("g-answer", "answer")
        conn.commit()
        stored = conn.execute(
            text("SELECT answer_image_finding FROM grade_results ORDER BY id")
        ).fetchall()
        assert [row[0] for row in stored] == ["answer", "blank"]

        # A trigger covers only the statements it names, so the UPDATE path
        # is its own assertion: a stored row must not be able to become
        # ``not_the_answer`` after the fact either.
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "UPDATE grade_results SET answer_image_finding = 'not_the_answer' "
                    "WHERE id = 'g-blank'"
                )
            )
        conn.rollback()
    finally:
        conn.close()
        engine.dispose()


def test_reviews_check_constraints_track_who_needs_an_ai_grade(db_url: str) -> None:
    """DB-level mirror of `Review.__post_init__` after Issue #118.

    ``approved`` still cannot exist without an AI grade -- there would be
    nothing to approve. ``modified`` can: a person grading a question whose
    AI attempt failed permanently has no AI row to have corrected, and
    fabricating one is exactly what Issue #97 refuses to do. The human grade
    stays required either way, so no ``modified`` row can be silent about
    what it decided.
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
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
                "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, created_at) "
                "VALUES ('s', 't', 'submissions/s/source.pdf', '" + ("3" * 64) + "', 1, "
                "'unprocessed', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO grade_results "
                "(id, submission_id, question_id, source, awarded, maximum, "
                "confidence, criteria, context, created_at) "
                "VALUES ('g-human', 's', 'q', 'human', 3, 5, 1.0, '[]', '[]', '2026-01-01')"
            )
        )
        conn.commit()

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO reviews "
                    "(id, submission_id, question_id, action, version, created_at) "
                    "VALUES ('rv-approved', 's', 'q', 'approved', 1, '2026-01-01')"
                )
            )
        conn.rollback()

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO reviews "
                    "(id, submission_id, question_id, action, version, created_at) "
                    "VALUES ('rv-modified', 's', 'q', 'modified', 1, '2026-01-01')"
                )
            )
        conn.rollback()

        conn.execute(
            text(
                "INSERT INTO reviews "
                "(id, submission_id, question_id, action, version, human_grade_result_id, "
                "created_at) "
                "VALUES ('rv-manual', 's', 'q', 'modified', 1, 'g-human', '2026-01-01')"
            )
        )
        conn.commit()
    finally:
        conn.close()
        engine.dispose()


_REVIEW_HISTORY_SEED = [
    "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
    "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')",
    "INSERT INTO questions (id, test_id, number, page, points, scoring_method) "
    "VALUES ('q', 't', '1', 1, 5, 'additive')",
    "INSERT INTO submissions "
    "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, created_at) "
    "VALUES ('s', 't', 'submissions/s/source.pdf', '" + ("4" * 64) + "', 1, "
    "'unprocessed', '2026-01-01')",
    "INSERT INTO grade_results "
    "(id, submission_id, question_id, source, awarded, maximum, confidence, "
    "criteria, context, created_at) "
    "VALUES ('g-ai', 's', 'q', 'ai', 4, 5, 0.9, '[]', '[]', '2026-01-01')",
    "INSERT INTO grade_results "
    "(id, submission_id, question_id, source, awarded, maximum, confidence, "
    "criteria, context, created_at) "
    "VALUES ('g-human', 's', 'q', 'human', 3, 5, 1.0, '[]', '[]', '2026-01-01')",
    "INSERT INTO jobs "
    "(id, kind, submission_id, question_id, state, attempts, max_attempts, "
    "created_at, updated_at) "
    "VALUES ('j', 'grading', 's', 'q', 'queued', 0, 3, '2026-01-01', '2026-01-01')",
    "INSERT INTO reviews "
    "(id, submission_id, question_id, action, version, ai_grade_result_id, created_at) "
    "VALUES ('rv-approved', 's', 'q', 'approved', 1, 'g-ai', '2026-01-01')",
    "INSERT INTO reviews "
    "(id, submission_id, question_id, action, version, human_grade_result_id, created_at) "
    "VALUES ('rv-modified', 's', 'q', 'modified', 2, 'g-human', '2026-01-01')",
    "INSERT INTO reviews "
    "(id, submission_id, question_id, action, version, regrade_job_id, created_at) "
    "VALUES ('rv-regrade', 's', 'q', 'regrade_requested', 3, 'j', '2026-01-01')",
    "INSERT INTO reviews "
    "(id, submission_id, question_id, action, version, undone_review_id, created_at) "
    "VALUES ('rv-undone', 's', 'q', 'undone', 4, 'rv-approved', '2026-01-01')",
]


def test_upgrade_repairs_a_review_history_that_could_not_be_deleted(db_url: str) -> None:
    """Issue #149: at 0017, deleting the test aborted on ``reviews``' own CHECKs.

    Each of the four references a CHECK makes mandatory carried ``ON DELETE
    SET NULL``, which rewrites the review row while it still exists. The
    ``undone`` one points back into ``reviews``, so no table order saved it:
    a test with a single undone review could not be deleted at all. 0018
    turns all four into ``ON DELETE CASCADE`` -- asserted here on a database
    that already holds the history, since that is the shape a real one is in.
    """
    upgrade(db_url, "0017")
    engine = create_sqlite_engine(db_url)
    try:
        with engine.begin() as conn:
            for statement in _REVIEW_HISTORY_SEED:
                conn.execute(text(statement))

        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text("DELETE FROM tests WHERE id = 't'"))
    finally:
        engine.dispose()

    upgrade(db_url, "head")

    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as conn:
            carried = conn.execute(text("SELECT id FROM reviews ORDER BY version")).fetchall()
            assert [row[0] for row in carried] == [
                "rv-approved",
                "rv-modified",
                "rv-regrade",
                "rv-undone",
            ]
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM tests WHERE id = 't'"))
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM reviews")).scalar() == 0
    finally:
        engine.dispose()


def test_confirmed_dependency_graph_row_requires_empty_unresolved(db_url: str) -> None:
    """DB-level mirror of `DependencyGraph.__post_init__`'s CONFIRMED invariant."""
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.commit()

        bad_graph = text(
            "INSERT INTO dependency_graphs "
            "(id, test_id, version, status, question_ids, unresolved, created_at, confirmed_at) "
            "VALUES ('t:v1', 't', 1, 'confirmed', '[\"q1\"]', "
            '\'[{"question_id": "q1", "reason": "x"}]\', \'2026-01-01\', \'2026-01-01\')'
        )
        with pytest.raises(IntegrityError):
            conn.execute(bad_graph)
    finally:
        conn.close()
        engine.dispose()


def test_dependency_graph_status_confirmed_at_pairing_is_enforced(db_url: str) -> None:
    """DB-level mirror of `DependencyGraph.__post_init__`'s CONFIRMED <=>
    confirmed_at-is-set invariant (Issue #26 review): a row bypassing the
    domain layer (repair, import, direct SQL) must not be able to insert
    status='confirmed' with confirmed_at=NULL, nor status='draft' with a
    non-null confirmed_at, or `DependencyGraph.from_dict` raises on every
    later GET/list of that row.
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.commit()

        confirmed_without_timestamp = text(
            "INSERT INTO dependency_graphs "
            "(id, test_id, version, status, question_ids, unresolved, created_at, confirmed_at) "
            "VALUES ('t:v1', 't', 1, 'confirmed', '[\"q1\"]', '[]', '2026-01-01', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(confirmed_without_timestamp)

        draft_with_timestamp = text(
            "INSERT INTO dependency_graphs "
            "(id, test_id, version, status, question_ids, unresolved, created_at, confirmed_at) "
            "VALUES ('t:v2', 't', 2, 'draft', '[\"q1\"]', '[]', '2026-01-01', '2026-01-01')"
        )
        with pytest.raises(IntegrityError):
            conn.execute(draft_with_timestamp)
    finally:
        conn.close()
        engine.dispose()


def test_dependency_graph_requires_non_empty_question_ids(db_url: str) -> None:
    """DB-level mirror of `DependencyGraph.__post_init__`'s non-empty
    `question_ids` invariant (Issue #26 review): a graph over zero questions
    is not a graph, and a row bypassing the domain layer (repair, import,
    direct SQL) must not be able to insert `question_ids = '[]'`, or
    `DependencyGraph.from_dict` raises on every later GET/list of that row.
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.commit()

        empty_question_ids = text(
            "INSERT INTO dependency_graphs "
            "(id, test_id, version, status, question_ids, unresolved, created_at, confirmed_at) "
            "VALUES ('t:v1', 't', 1, 'draft', '[]', '[]', '2026-01-01', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(empty_question_ids)
    finally:
        conn.close()
        engine.dispose()


def test_dependency_edge_invariants_are_enforced(db_url: str) -> None:
    """DB-level mirror of `DependencyEdge.__post_init__`'s self-loop,
    non-empty-`provides`, and non-blank-`rationale` invariants (Issue #26
    review): a row bypassing the domain layer (repair, import, direct SQL)
    must not be able to insert any of these, or hydrating that graph raises
    on every later GET/list of it.
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO dependency_graphs "
                "(id, test_id, version, status, question_ids, unresolved, created_at, "
                "confirmed_at) "
                "VALUES ('t:v1', 't', 1, 'draft', '[\"q1\", \"q2\"]', '[]', "
                "'2026-01-01', NULL)"
            )
        )
        conn.commit()

        self_loop = text(
            "INSERT INTO dependency_edges "
            "(graph_id, from_question_id, to_question_id, provides, rationale, confidence) "
            "VALUES ('t:v1', 'q1', 'q1', '[\"recognized_text\"]', 'x', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(self_loop)

        empty_provides = text(
            "INSERT INTO dependency_edges "
            "(graph_id, from_question_id, to_question_id, provides, rationale, confidence) "
            "VALUES ('t:v1', 'q1', 'q2', '[]', 'x', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(empty_provides)

        blank_rationale = text(
            "INSERT INTO dependency_edges "
            "(graph_id, from_question_id, to_question_id, provides, rationale, confidence) "
            "VALUES ('t:v1', 'q1', 'q2', '[\"recognized_text\"]', '   ', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(blank_rationale)
    finally:
        conn.close()
        engine.dispose()


def test_dependency_edge_provides_rejects_unknown_values(db_url: str) -> None:
    """`json_valid`/`json_array_length` alone only check JSON shape, not
    element values -- a row bypassing the domain layer (repair, import,
    direct SQL) could still insert `provides = '["bogus"]'`, which
    `DependencyProvision(...)` rejects the next time that graph is hydrated.
    SQLite CHECK constraints cannot contain subqueries, so this is enforced
    by `trg_dependency_edges_provides_known_values_insert`/`_update` triggers
    instead (Issue #26 review).
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO dependency_graphs "
                "(id, test_id, version, status, question_ids, unresolved, created_at, "
                "confirmed_at) "
                "VALUES ('t:v1', 't', 1, 'draft', '[\"q1\", \"q2\"]', '[]', "
                "'2026-01-01', NULL)"
            )
        )
        conn.commit()

        unknown_provides = text(
            "INSERT INTO dependency_edges "
            "(graph_id, from_question_id, to_question_id, provides, rationale, confidence) "
            "VALUES ('t:v1', 'q1', 'q2', '[\"bogus\"]', 'x', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(unknown_provides)

        conn.execute(
            text(
                "INSERT INTO dependency_edges "
                "(graph_id, from_question_id, to_question_id, provides, rationale, confidence) "
                "VALUES ('t:v1', 'q1', 'q2', '[\"recognized_text\"]', 'x', NULL)"
            )
        )
        conn.commit()

        update_to_unknown_provides = text(
            "UPDATE dependency_edges SET provides = '[\"bogus\"]' "
            "WHERE graph_id = 't:v1' AND from_question_id = 'q1' AND to_question_id = 'q2'"
        )
        with pytest.raises(IntegrityError):
            conn.execute(update_to_unknown_provides)
    finally:
        conn.close()
        engine.dispose()


def test_dependency_edge_provides_rejects_a_null_element(db_url: str) -> None:
    """`value NOT IN (...)` alone does not catch a JSON `null` element -- SQL's
    `NULL NOT IN (...)` evaluates to NULL, which `WHERE` treats as "don't
    select this row" -- so the known-values triggers must check `value IS
    NULL` explicitly too (Issue #26 review).
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO dependency_graphs "
                "(id, test_id, version, status, question_ids, unresolved, created_at, "
                "confirmed_at) "
                "VALUES ('t:v1', 't', 1, 'draft', '[\"q1\", \"q2\"]', '[]', "
                "'2026-01-01', NULL)"
            )
        )
        conn.commit()

        null_provides_element = text(
            "INSERT INTO dependency_edges "
            "(graph_id, from_question_id, to_question_id, provides, rationale, confidence) "
            "VALUES ('t:v1', 'q1', 'q2', '[\"recognized_text\", null]', 'x', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(null_provides_element)
    finally:
        conn.close()
        engine.dispose()


def test_dependency_graph_question_ids_rejects_a_null_or_blank_element(db_url: str) -> None:
    """`json_valid`/`json_array_length` alone only check that `question_ids`
    is a non-empty JSON array, not that every element is a (non-blank)
    string -- a row bypassing the domain layer could still insert
    `["q1", null]`, which `DependencyGraph` (a `frozenset[str]`) and every
    downstream consumer expect never to see (Issue #26 review).
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.commit()

        null_element = text(
            "INSERT INTO dependency_graphs "
            "(id, test_id, version, status, question_ids, unresolved, created_at, "
            "confirmed_at) "
            "VALUES ('t:v1', 't', 1, 'draft', '[\"q1\", null]', '[]', '2026-01-01', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(null_element)

        blank_element = text(
            "INSERT INTO dependency_graphs "
            "(id, test_id, version, status, question_ids, unresolved, created_at, "
            "confirmed_at) "
            "VALUES ('t:v2', 't', 2, 'draft', '[\"q1\", \"   \"]', '[]', '2026-01-01', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(blank_element)
    finally:
        conn.close()
        engine.dispose()


def test_dependency_graph_unresolved_shape_and_elements_are_enforced(db_url: str) -> None:
    """`ck_dependency_graphs_confirmed_has_no_unresolved` only constrains
    CONFIRMED rows -- a DRAFT row had no shape requirement on `unresolved` at
    all, and even a valid, non-empty array could still contain a malformed
    element (missing `question_id`/`reason`). `DependencyGraph.from_dict`
    always iterates it expecting question/reason objects (Issue #26 review).
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.commit()

        non_array_unresolved = text(
            "INSERT INTO dependency_graphs "
            "(id, test_id, version, status, question_ids, unresolved, created_at, "
            "confirmed_at) "
            "VALUES ('t:v1', 't', 1, 'draft', '[\"q1\"]', '{}', '2026-01-01', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(non_array_unresolved)

        malformed_element = text(
            "INSERT INTO dependency_graphs "
            "(id, test_id, version, status, question_ids, unresolved, created_at, "
            "confirmed_at) "
            "VALUES ('t:v2', 't', 2, 'draft', '[\"q1\"]', "
            "'[{\"question_id\": \"q1\"}]', '2026-01-01', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(malformed_element)
    finally:
        conn.close()
        engine.dispose()


def test_dependency_edge_endpoints_must_belong_to_the_graph(db_url: str) -> None:
    """The primary key / self-loop / non-empty checks never verify an edge's
    endpoints actually belong to its own graph's `question_ids` snapshot --
    a row bypassing the domain layer could persist an edge referencing a
    question that was never part of that graph version, and
    `DependencyGraph.__post_init__` raises `UnknownQuestionError` the next
    time it is hydrated (Issue #26 review).
    """
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO dependency_graphs "
                "(id, test_id, version, status, question_ids, unresolved, created_at, "
                "confirmed_at) "
                "VALUES ('t:v1', 't', 1, 'draft', '[\"q1\", \"q2\"]', '[]', "
                "'2026-01-01', NULL)"
            )
        )
        conn.commit()

        unknown_endpoint = text(
            "INSERT INTO dependency_edges "
            "(graph_id, from_question_id, to_question_id, provides, rationale, confidence) "
            "VALUES ('t:v1', 'q1', 'q999', '[\"recognized_text\"]', 'x', NULL)"
        )
        with pytest.raises(IntegrityError):
            conn.execute(unknown_endpoint)
    finally:
        conn.close()
        engine.dispose()


def test_job_dependency_graph_version_must_be_positive(db_url: str) -> None:
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    conn = engine.connect()
    try:
        conn.execute(
            text(
                "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                "VALUES ('t', 'n', 'additive', 'draft', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO submissions "
                "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, "
                "created_at) "
                "VALUES ('sub', 't', 'submissions/sub/source.pdf', '" + ("0" * 64) + "', 1, "
                "'unprocessed', '2026-01-01')"
            )
        )
        conn.commit()

        bad_job = text(
            "INSERT INTO jobs "
            "(id, kind, submission_id, state, attempts, max_attempts, "
            "dependency_graph_version, created_at, updated_at) "
            "VALUES ('job', 'grading', 'sub', 'queued', 0, 3, 0, '2026-01-01', '2026-01-01')"
        )
        with pytest.raises(IntegrityError):
            conn.execute(bad_job)
    finally:
        conn.close()
        engine.dispose()


def test_migration_file_paths_exist() -> None:
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    names = {p.name for p in versions.glob("*.py")}
    assert {
        "0001_initial_schema.py",
        "0002_operation_log.py",
        "0003_dependency_graph.py",
        "0004_job_dependency_graph_version.py",
        "0005_answer_intake.py",
        "0006_student_label_length.py",
        "0007_original_filename_length.py",
        "0008_job_queue_fields.py",
        "0009_job_usable_allows_failed.py",
        "0010_recognition_text_length.py",
        "0011_test_status.py",
        "0012_grade_result_ai_metadata.py",
        "0013_review_history_edit.py",
        "0014_exports.py",
        "0015_test_materials.py",
        "0016_manual_grade_without_ai.py",
        "0017_grade_result_answer_image_finding.py",
        "0018_review_reference_cascade.py",
        "0019_two_page_question_areas.py",
        "0020_grade_result_token_usage.py",
        "0021_error_catalog.py",
    } <= names


def test_0019_two_page_question_areas_upgrade_and_downgrade(db_url: str) -> None:
    upgrade(db_url, "0018")
    assert current_revision(db_url) == "0018"
    engine = create_sqlite_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                    "VALUES ('t1', 'Test 1', 'additive', 'ready', '2026-01-01')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO questions (id, test_id, number, page, points, scoring_method) "
                    "VALUES ('q1', 't1', '1', 1, 5, 'additive')"
                )
            )
    finally:
        engine.dispose()

    upgrade(db_url, "0019")
    assert current_revision(db_url) == "0019"
    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, page, page_2, answer_area_2 FROM questions WHERE id = 'q1'")
            ).fetchone()
            assert row is not None
            assert row[0] == "q1"
            assert row[1] == 1
            assert row[2] is None
            assert row[3] is None

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO questions (id, test_id, number, page, points, scoring_method, "
                    "page_2, answer_area_2) "
                    "VALUES ('q2', 't1', '2', 1, 10, 'additive', 2, :area)"
                ),
                {"area": '{"x": 0.1}'},
            )
    finally:
        engine.dispose()

    downgrade(db_url, "0018")
    assert current_revision(db_url) == "0018"
    engine = create_sqlite_engine(db_url)
    try:
        cols = {col["name"] for col in inspect(engine).get_columns("questions")}
        assert "page_2" not in cols
        assert "answer_area_2" not in cols
    finally:
        engine.dispose()


def test_0019_question_check_constraints(db_url: str) -> None:
    upgrade(db_url, "head")
    engine = create_sqlite_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                    "VALUES ('t1', 'Test 1', 'additive', 'ready', '2026-01-01')"
                )
            )

        # 1. page_2 < 1 fails ck_questions_page_2_positive
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO questions (id, test_id, number, page, points, scoring_method, "
                    "page_2, answer_area_2) "
                    "VALUES ('q_bad_p2', 't1', '1', 1, 5, 'additive', 0, :area)"
                ),
                {"area": '{"x": 0.1}'},
            )

        # 2. page_2 <= page fails ck_questions_page_2_greater
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO questions (id, test_id, number, page, points, scoring_method, "
                    "page_2, answer_area_2) "
                    "VALUES ('q_bad_order', 't1', '2', 2, 5, 'additive', 2, :area)"
                ),
                {"area": '{"x": 0.1}'},
            )

        # 3. page_2 without answer_area_2 fails ck_questions_page_2_and_area_2_paired
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO questions (id, test_id, number, page, points, scoring_method, "
                    "page_2, answer_area_2) "
                    "VALUES ('q_missing_area2', 't1', '3', 1, 5, 'additive', 2, NULL)"
                )
            )

        # 4. answer_area_2 without page_2 fails ck_questions_page_2_and_area_2_paired
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO questions (id, test_id, number, page, points, scoring_method, "
                    "page_2, answer_area_2) "
                    "VALUES ('q_missing_page2', 't1', '4', 1, 5, 'additive', NULL, :area)"
                ),
                {"area": '{"x": 0.1}'},
            )

        # 5. answer_area_2 = 'null' with page_2 is rejected
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO questions (id, test_id, number, page, points, scoring_method, "
                    "page_2, answer_area_2) "
                    "VALUES ('q_null_str', 't1', '5', 1, 5, 'additive', 2, 'null')"
                )
            )
    finally:
        engine.dispose()


def test_0020_grade_result_token_usage_upgrade_and_downgrade(db_url: str) -> None:
    upgrade(db_url, "0019")
    engine = create_sqlite_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                    "VALUES ('t1', 'Test 1', 'additive', 'ready', '2026-01-01')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO submissions "
                    "(id, test_id, source_pdf_path, source_pdf_sha256, page_count, state, "
                    "created_at) VALUES ('s1', 't1', 'submissions/s1/source.pdf', :sha, 1, "
                    "'unprocessed', '2026-01-01')"
                ),
                {"sha": "0" * 64},
            )
            conn.execute(
                text(
                    "INSERT INTO questions (id, test_id, number, page, points, scoring_method) "
                    "VALUES ('q1', 't1', '1', 1, 5, 'additive')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO grade_results "
                    "(id, submission_id, question_id, source, awarded, maximum, confidence, "
                    "criteria, context, created_at, provider, model, prompt_version) "
                    "VALUES ('g1', 's1', 'q1', 'ai', 1, 5, 0.9, '[]', '[]', '2026-01-01', "
                    "'openrouter', 'test/model', 'v1')"
                )
            )
    finally:
        engine.dispose()

    upgrade(db_url, "head")
    assert current_revision(db_url) == "0021"
    engine = create_sqlite_engine(db_url)
    try:
        cols = {col["name"] for col in inspect(engine).get_columns("grade_results")}
        assert {"input_tokens", "output_tokens"} <= cols
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE grade_results SET input_tokens = 10, output_tokens = 5 WHERE id = 'g1'"
                )
            )
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE grade_results SET input_tokens = 10, output_tokens = NULL "
                    "WHERE id = 'g1'"
                )
            )
    finally:
        engine.dispose()

    downgrade(db_url, "0019")
    assert current_revision(db_url) == "0019"
    engine = create_sqlite_engine(db_url)
    try:
        cols = {col["name"] for col in inspect(engine).get_columns("grade_results")}
        assert "input_tokens" not in cols
        assert "output_tokens" not in cols
    finally:
        engine.dispose()


def test_0021_error_catalog_upgrade_and_downgrade(db_url: str) -> None:
    """Issue #209: the reviewed 誤答カタログ becomes a real table, one row per
    test, with its revision and entries checked by the database."""
    upgrade(db_url, "0020")
    assert current_revision(db_url) == "0020"
    assert "error_catalogs" not in _tables(db_url)

    engine = create_sqlite_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                    "VALUES ('t1', 'Test 1', 'additive', 'ready', '2026-01-01')"
                )
            )
    finally:
        engine.dispose()

    upgrade(db_url, "head")
    assert current_revision(db_url) == "0021"
    engine = create_sqlite_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                    "VALUES ('t2', 'Test 2', 'additive', 'ready', '2026-01-01')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO tests (id, name, default_scoring_method, status, created_at) "
                    "VALUES ('t3', 'Test 3', 'additive', 'ready', '2026-01-01')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO error_catalogs "
                    "(test_id, revision, imported, import_error, note, entries) "
                    "VALUES ('t1', 1, 0, NULL, NULL, "
                    '\'[{"mistake": "x", "red_ink": "y", "edited": true}]\')'
                )
            )
        # A row written outside the domain must still respect the constraints.
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO error_catalogs "
                    "(test_id, revision, imported, import_error, note, entries) "
                    "VALUES ('t2', 0, 0, NULL, NULL, '[]')"
                )
            )
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO error_catalogs "
                    "(test_id, revision, imported, import_error, note, entries) "
                    "VALUES ('t3', 1, 0, NULL, NULL, '{}')"
                )
            )
    finally:
        engine.dispose()

    downgrade(db_url, "0020")
    assert current_revision(db_url) == "0020"
    assert "error_catalogs" not in _tables(db_url)
