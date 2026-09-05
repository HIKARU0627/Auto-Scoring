"""add dependency_graphs and dependency_edges tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-04

Adds the question dependency-graph tables (Issue #26): one row per
(test, version) in ``dependency_graphs``, its edges in ``dependency_edges``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_dependency_graph_status = sa.Enum(
    "draft", "confirmed", name="dependencygraphstatus", native_enum=False
)


def upgrade() -> None:
    op.create_table(
        "dependency_graphs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "test_id",
            sa.String(),
            sa.ForeignKey("tests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", _dependency_graph_status, nullable=False),
        sa.Column("question_ids", sa.JSON(), nullable=False),
        sa.Column("unresolved", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("test_id", "version", name="uq_dependency_graphs_test_version"),
        sa.CheckConstraint("version >= 1", name="ck_dependency_graphs_version_positive"),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed')", name="ck_dependency_graphs_status_valid"
        ),
        sa.CheckConstraint(
            "status != 'confirmed' OR json_array_length(unresolved) = 0",
            name="ck_dependency_graphs_confirmed_has_no_unresolved",
        ),
        # The check above only constrains CONFIRMED rows -- a DRAFT row had
        # no shape requirement at all, so a row written outside the domain
        # (repair, import, direct SQL) could persist `unresolved = 'null'`,
        # `'{}'`, or a bare scalar (`json_array_length` returns 0 for all of
        # those, so they would even slip past a CONFIRMED row's check
        # above). `DependencyGraph.from_dict` always iterates
        # `data["unresolved"]` expecting a JSON array, and hydration blows
        # up on anything else (Issue #26 review). Applies regardless of
        # status.
        sa.CheckConstraint(
            "json_valid(unresolved) AND json_type(unresolved) = 'array'",
            name="ck_dependency_graphs_unresolved_is_array",
        ),
        # Mirrors DependencyGraph.__post_init__: CONFIRMED <=> confirmed_at is
        # set. Without this, a row written outside the domain layer (repair,
        # import, direct SQL) with status='confirmed' and confirmed_at=NULL
        # (or the reverse) would be accepted by the DB but rejected by
        # `DependencyGraph`'s own constructor on hydration, turning every
        # GET/list of that row into a 500 (Issue #26 review).
        sa.CheckConstraint(
            "(status = 'confirmed') = (confirmed_at IS NOT NULL)",
            name="ck_dependency_graphs_confirmed_at_matches_status",
        ),
        # Mirrors DependencyGraph.__post_init__: `question_ids` must be
        # non-empty (a graph over zero questions is not a graph). Without
        # this, a row written outside the domain layer (repair, import,
        # direct SQL) could persist `question_ids = '[]'` and every later
        # GET/list of it would raise on hydration (Issue #26 review).
        sa.CheckConstraint(
            "json_valid(question_ids) AND json_array_length(question_ids) > 0",
            name="ck_dependency_graphs_question_ids_non_empty",
        ),
    )
    op.create_index("ix_dependency_graphs_test_id", "dependency_graphs", ["test_id"])

    op.create_table(
        "dependency_edges",
        sa.Column(
            "graph_id",
            sa.String(),
            sa.ForeignKey("dependency_graphs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("from_question_id", sa.String(), primary_key=True),
        sa.Column("to_question_id", sa.String(), primary_key=True),
        sa.Column("provides", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_dependency_edges_confidence_range",
        ),
        # Mirrors `DependencyEdge.__post_init__`'s remaining invariants: a
        # row written outside the domain (repair, import, direct SQL) could
        # otherwise persist a self-loop, or an edge with no `provides`/blank
        # `rationale`, and hydrating that graph would raise `SelfLoopError`/
        # `DependencyGraphError`, breaking every API call touching it (Issue
        # #26 review).
        sa.CheckConstraint(
            "from_question_id != to_question_id", name="ck_dependency_edges_no_self_loop"
        ),
        # `domain.models._require_non_empty` requires both endpoint ids to
        # be non-blank strings; the self-loop check above compares them to
        # each other but never checks either against blank on its own
        # (Issue #26 review).
        sa.CheckConstraint(
            "length(trim(from_question_id)) > 0",
            name="ck_dependency_edges_from_question_id_non_empty",
        ),
        sa.CheckConstraint(
            "length(trim(to_question_id)) > 0",
            name="ck_dependency_edges_to_question_id_non_empty",
        ),
        sa.CheckConstraint(
            "json_valid(provides) AND json_array_length(provides) > 0",
            name="ck_dependency_edges_provides_non_empty",
        ),
        sa.CheckConstraint(
            "length(trim(rationale)) > 0", name="ck_dependency_edges_rationale_non_empty"
        ),
    )
    op.create_index("ix_dependency_edges_graph_id", "dependency_edges", ["graph_id"])

    # The invariants below all need `json_each`, a table-valued function, to
    # inspect array *elements* -- and SQLite's `CHECK` constraints cannot
    # contain subqueries (including table-valued functions), so every one of
    # these is a pair of `BEFORE INSERT`/`BEFORE UPDATE OF <col>` triggers
    # instead of a `CheckConstraint`. All are mirrored in `db/orm.py`.

    # `provides_non_empty` above only checks JSON shape, not element values --
    # a row written outside the domain (repair, import, direct SQL) could
    # still persist e.g. `provides = '["bogus"]'` or `provides = '[null]'`,
    # which `DependencyProvision(...)` rejects with a `ValueError` the next
    # time that graph is hydrated (Issue #26 review). `value NOT IN (...)`
    # alone does not catch a JSON `null` element -- SQL's `NULL NOT IN (...)`
    # evaluates to NULL (neither true nor false), which `WHERE` treats as
    # "don't select this row" -- so `value IS NULL` must be checked
    # explicitly. Keep the value list in sync with
    # `domain.dependency_graph.DependencyProvision`'s members.
    op.execute(
        """
        CREATE TRIGGER trg_dependency_edges_provides_known_values_insert
        BEFORE INSERT ON dependency_edges
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1 FROM json_each(NEW.provides)
            WHERE value IS NULL OR value NOT IN ('recognized_text', 'score', 'criterion_result')
        )
        BEGIN
            SELECT RAISE(ABORT, 'dependency_edges.provides contains an unknown value');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_dependency_edges_provides_known_values_update
        BEFORE UPDATE OF provides ON dependency_edges
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1 FROM json_each(NEW.provides)
            WHERE value IS NULL OR value NOT IN ('recognized_text', 'score', 'criterion_result')
        )
        BEGIN
            SELECT RAISE(ABORT, 'dependency_edges.provides contains an unknown value');
        END;
        """
    )

    # `ck_dependency_graphs_question_ids_non_empty` only checks that
    # `question_ids` is a non-empty JSON array, not that every element is a
    # (non-blank) string -- a row written outside the domain could persist
    # `question_ids = '[null]'` or `'["q1", null]'`, and `DependencyGraph`'s
    # own type (`frozenset[str]`) plus every downstream consumer expects
    # plain strings, not `None` (Issue #26 review).
    op.execute(
        """
        CREATE TRIGGER trg_dependency_graphs_question_ids_elements_insert
        BEFORE INSERT ON dependency_graphs
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1 FROM json_each(NEW.question_ids)
            WHERE json_each.type IS NOT 'text' OR length(trim(json_each.value)) = 0
        )
        BEGIN
            SELECT RAISE(
                ABORT, 'dependency_graphs.question_ids contains a non-string or blank value'
            );
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_dependency_graphs_question_ids_elements_update
        BEFORE UPDATE OF question_ids ON dependency_graphs
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1 FROM json_each(NEW.question_ids)
            WHERE json_each.type IS NOT 'text' OR length(trim(json_each.value)) = 0
        )
        BEGIN
            SELECT RAISE(
                ABORT, 'dependency_graphs.question_ids contains a non-string or blank value'
            );
        END;
        """
    )

    # `ck_dependency_graphs_unresolved_is_array` only checks the outer JSON
    # shape -- each element must additionally be an object matching
    # `UnresolvedQuestion`'s shape (non-blank string `question_id`/`reason`),
    # or `UnresolvedQuestion.from_dict` raises the next time that graph is
    # hydrated (Issue #26 review).
    op.execute(
        """
        CREATE TRIGGER trg_dependency_graphs_unresolved_elements_insert
        BEFORE INSERT ON dependency_graphs
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1 FROM json_each(NEW.unresolved)
            WHERE json_each.type IS NOT 'object'
               OR json_type(json_each.value, '$.question_id') IS NOT 'text'
               OR length(trim(json_extract(json_each.value, '$.question_id'))) = 0
               OR json_type(json_each.value, '$.reason') IS NOT 'text'
               OR length(trim(json_extract(json_each.value, '$.reason'))) = 0
        )
        BEGIN
            SELECT RAISE(ABORT, 'dependency_graphs.unresolved contains a malformed entry');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_dependency_graphs_unresolved_elements_update
        BEFORE UPDATE OF unresolved ON dependency_graphs
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1 FROM json_each(NEW.unresolved)
            WHERE json_each.type IS NOT 'object'
               OR json_type(json_each.value, '$.question_id') IS NOT 'text'
               OR length(trim(json_extract(json_each.value, '$.question_id'))) = 0
               OR json_type(json_each.value, '$.reason') IS NOT 'text'
               OR length(trim(json_extract(json_each.value, '$.reason'))) = 0
        )
        BEGIN
            SELECT RAISE(ABORT, 'dependency_graphs.unresolved contains a malformed entry');
        END;
        """
    )

    # The primary key / self-loop / non-empty checks above never verify an
    # edge's endpoints actually belong to its own graph's `question_ids`
    # snapshot -- a row written outside the domain (repair, import, direct
    # SQL) could persist an edge whose `from_question_id`/`to_question_id`
    # names a question that was never part of that graph version, and
    # `DependencyGraph.__post_init__` raises `UnknownQuestionError` the next
    # time it is hydrated, breaking every read of that graph (Issue #26
    # review). This needs a join against the parent `dependency_graphs` row.
    op.execute(
        """
        CREATE TRIGGER trg_dependency_edges_endpoints_known_insert
        BEFORE INSERT ON dependency_edges
        FOR EACH ROW
        WHEN
            NOT EXISTS (
                SELECT 1 FROM dependency_graphs g, json_each(g.question_ids) qi
                WHERE g.id = NEW.graph_id AND qi.value = NEW.from_question_id
            )
            OR NOT EXISTS (
                SELECT 1 FROM dependency_graphs g, json_each(g.question_ids) qi
                WHERE g.id = NEW.graph_id AND qi.value = NEW.to_question_id
            )
        BEGIN
            SELECT RAISE(ABORT, 'dependency_edges endpoint is not in its graph''s question_ids');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_dependency_edges_endpoints_known_update
        BEFORE UPDATE OF graph_id, from_question_id, to_question_id ON dependency_edges
        FOR EACH ROW
        WHEN
            NOT EXISTS (
                SELECT 1 FROM dependency_graphs g, json_each(g.question_ids) qi
                WHERE g.id = NEW.graph_id AND qi.value = NEW.from_question_id
            )
            OR NOT EXISTS (
                SELECT 1 FROM dependency_graphs g, json_each(g.question_ids) qi
                WHERE g.id = NEW.graph_id AND qi.value = NEW.to_question_id
            )
        BEGIN
            SELECT RAISE(ABORT, 'dependency_edges endpoint is not in its graph''s question_ids');
        END;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_dependency_edges_endpoints_known_update")
    op.execute("DROP TRIGGER IF EXISTS trg_dependency_edges_endpoints_known_insert")
    op.execute("DROP TRIGGER IF EXISTS trg_dependency_graphs_unresolved_elements_update")
    op.execute("DROP TRIGGER IF EXISTS trg_dependency_graphs_unresolved_elements_insert")
    op.execute("DROP TRIGGER IF EXISTS trg_dependency_graphs_question_ids_elements_update")
    op.execute("DROP TRIGGER IF EXISTS trg_dependency_graphs_question_ids_elements_insert")
    op.execute("DROP TRIGGER IF EXISTS trg_dependency_edges_provides_known_values_update")
    op.execute("DROP TRIGGER IF EXISTS trg_dependency_edges_provides_known_values_insert")
    op.drop_index("ix_dependency_edges_graph_id", table_name="dependency_edges")
    op.drop_table("dependency_edges")
    op.drop_index("ix_dependency_graphs_test_id", table_name="dependency_graphs")
    op.drop_table("dependency_graphs")
