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
        sa.CheckConstraint(
            "json_valid(provides) AND json_array_length(provides) > 0",
            name="ck_dependency_edges_provides_non_empty",
        ),
        sa.CheckConstraint(
            "length(trim(rationale)) > 0", name="ck_dependency_edges_rationale_non_empty"
        ),
    )
    op.create_index("ix_dependency_edges_graph_id", "dependency_edges", ["graph_id"])


def downgrade() -> None:
    op.drop_index("ix_dependency_edges_graph_id", table_name="dependency_edges")
    op.drop_table("dependency_edges")
    op.drop_index("ix_dependency_graphs_test_id", table_name="dependency_graphs")
    op.drop_table("dependency_graphs")
