"""add grade_results AI grading metadata columns

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-06

GitHub Issue #20 (parent #3): the production `AIProvider` grading pipeline
needs to persist, alongside the existing score/confidence/criteria/rationale
columns (0001), the pieces `auto_scoring.domain.models.GradeResult` gained
for this Issue:

- ``comment``: the AI's overall comment for the question
  (simplified-design-specification.md section 16.5's "コメント" review-UI
  field), mirroring the 120-character cap already enforced on annotation
  comments (``domain.models.MAX_COMMENT_CHARS``).
- ``provider``/``model``/``prompt_version``: the AI reproducibility triple
  (Issue #20 acceptance: "provider/model/prompt versionが追跡でき"),
  recorded together or not at all -- a human-confirmed row has no such call
  to reproduce.
- ``dependency_graph_version``: the confirmed `DependencyGraph` version
  (Issue #26) in effect when this grade was produced, mirroring
  ``jobs.dependency_graph_version`` (0004).
- ``context``: which prerequisite ``recognition_results``/``grade_results``
  row(s) fed this grade (Issue #20 additional acceptance: "使用した...前提
  result versionをGradeResultへ記録し、前提が更新された場合は古い下流結果を
  再利用しない"), as a JSON list of
  ``{question_id, recognition_result_id, grade_result_id}``.

All five columns are nullable/empty-default: every existing row (a
human-confirmed grade, or an AI grade recorded before this Issue) simply has
no such metadata. ``context`` gets a transient ``server_default`` of ``'[]'``
for the existing-rows backfill, then has it dropped in a second batch pass --
the same two-pass pattern ``0005``/``0011`` used -- so a later ``INSERT`` that
omits ``context`` fails loudly (``NOT NULL``) rather than silently defaulting,
matching ``GradeResultRow.context``'s ORM-side default (Python ``list``, not
a DB default) applying only through the ORM/mapper path.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrors domain.models.MAX_COMMENT_CHARS. Migrations hardcode their own
#: literals rather than importing application code.
_MAX_COMMENT_CHARS = 120


def upgrade() -> None:
    with op.batch_alter_table("grade_results", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("comment", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("provider", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("model", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("prompt_version", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("dependency_graph_version", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("context", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch_op.create_check_constraint(
            "ck_grade_results_comment_length",
            f"comment IS NULL OR length(comment) <= {_MAX_COMMENT_CHARS}",
        )
        batch_op.create_check_constraint(
            "ck_grade_results_ai_metadata_complete",
            "(provider IS NULL AND model IS NULL AND prompt_version IS NULL) OR "
            "(provider IS NOT NULL AND model IS NOT NULL AND prompt_version IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_grade_results_dependency_graph_version_positive",
            "dependency_graph_version IS NULL OR dependency_graph_version >= 1",
        )

    with op.batch_alter_table("grade_results") as batch_op:
        batch_op.alter_column("context", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("grade_results", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "ck_grade_results_dependency_graph_version_positive", type_="check"
        )
        batch_op.drop_constraint("ck_grade_results_ai_metadata_complete", type_="check")
        batch_op.drop_constraint("ck_grade_results_comment_length", type_="check")
        batch_op.drop_column("context")
        batch_op.drop_column("dependency_graph_version")
        batch_op.drop_column("prompt_version")
        batch_op.drop_column("model")
        batch_op.drop_column("provider")
        batch_op.drop_column("comment")
