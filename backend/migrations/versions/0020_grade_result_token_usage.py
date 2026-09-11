"""record provider token usage on grade results

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-11

GitHub Issue #187 (parent #3). Nullable input/output token counts on
grade_results for AI-sourced rows only. No backfill -- historical rows stay
NULL meaning "provider did not report usage at record time".

Uses ``ADD COLUMN`` and triggers rather than ``batch_alter_table`` so the
``answer_image_finding`` triggers from 0017 survive (a rebuild drops them;
see 0017's docstring).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INVALID_TOKEN_MESSAGE = "grade_results token counts invalid"

_TOKEN_TRIGGERS = {
    "trg_grade_results_token_counts_valid_insert": "INSERT ON grade_results",
    "trg_grade_results_token_counts_valid_update": (
        "UPDATE OF input_tokens, output_tokens, source ON grade_results"
    ),
}


def _create_token_triggers() -> None:
    for name, event in _TOKEN_TRIGGERS.items():
        op.execute(
            f"""
            CREATE TRIGGER {name}
            BEFORE {event}
            FOR EACH ROW
            WHEN (
                (NEW.input_tokens IS NULL) != (NEW.output_tokens IS NULL)
                OR NEW.input_tokens < 0
                OR NEW.output_tokens < 0
                OR (
                    (NEW.input_tokens IS NOT NULL OR NEW.output_tokens IS NOT NULL)
                    AND NEW.source != 'ai'
                )
            )
            BEGIN
                SELECT RAISE(ABORT, '{_INVALID_TOKEN_MESSAGE}');
            END;
            """
        )


def upgrade() -> None:
    op.add_column("grade_results", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("grade_results", sa.Column("output_tokens", sa.Integer(), nullable=True))
    _create_token_triggers()


def downgrade() -> None:
    for name in _TOKEN_TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    op.drop_column("grade_results", "output_tokens")
    op.drop_column("grade_results", "input_tokens")
