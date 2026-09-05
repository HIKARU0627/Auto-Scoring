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

    assert current_revision(db_url) == "0004"
    assert not decoy_path.exists()


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
                "INSERT INTO tests (id, name, default_scoring_method, created_at) "
                "VALUES ('t', 'n', 'additive', '2026-01-01')"
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
                "INSERT INTO tests (id, name, default_scoring_method, created_at) "
                "VALUES ('t', 'n', 'additive', '2026-01-01')"
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
