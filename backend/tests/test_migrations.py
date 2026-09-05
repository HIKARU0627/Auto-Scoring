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
    assert current_revision(db_url) == "0004"


def test_one_generation_old_database_upgrades_to_head(db_url: str) -> None:
    # A database created before 0002 existed.
    upgrade(db_url, "0001")
    assert "operation_log" not in _tables(db_url)

    upgrade(db_url, "head")
    assert "operation_log" in _tables(db_url)
    assert current_revision(db_url) == "0004"


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


def test_confirmed_dependency_graph_row_requires_empty_unresolved(db_url: str) -> None:
    """DB-level mirror of `DependencyGraph.__post_init__`'s CONFIRMED invariant."""
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
                "INSERT INTO tests (id, name, default_scoring_method, created_at) "
                "VALUES ('t', 'n', 'additive', '2026-01-01')"
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
                "INSERT INTO tests (id, name, default_scoring_method, created_at) "
                "VALUES ('t', 'n', 'additive', '2026-01-01')"
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
                "INSERT INTO tests (id, name, default_scoring_method, created_at) "
                "VALUES ('t', 'n', 'additive', '2026-01-01')"
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


def test_job_dependency_graph_version_must_be_positive(db_url: str) -> None:
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
    } <= names
