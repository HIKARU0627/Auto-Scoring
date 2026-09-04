"""add answer intake columns and answer_images table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-04

Issue #17 (answer PDF intake / storage / image preprocessing):

* ``submissions`` gains ``source_pdf_sha256`` (reintake dedupe key),
  ``page_count`` (learned once at intake), ``original_filename`` and
  ``review_reason`` (why intake routed a submission to ``needs_review``).
* new table ``answer_images``: the per-question answer-area image extracted
  from a submission (docs/answer-intake-and-preprocessing.md).

SQLite cannot add a ``CHECK`` constraint to an existing table without
recreating it, so the ``submissions`` alteration uses Alembic's batch mode
(``recreate="always"``), which reflects the existing table -- including its
``ck_submissions_state_valid`` check constraint -- and rebuilds it with the
new columns and the new ``ck_submissions_page_count_positive`` check.

Backfill: a database created before this revision has submission rows with
no ``source_pdf_sha256``/``page_count`` of their own. The column defaults
above only cover the *shape* of those rows (``""`` / ``1``) so the ``ADD
COLUMN`` succeeds; ``Submission.__post_init__`` (``domain/models.py``)
rejects an empty ``source_pdf_sha256``, so left as ``""`` those rows would
fail to load the moment this revision lands. ``_backfill_submission_metadata``
recomputes the real hash and page count from each submission's still-present
``source.pdf`` (Issue #11: the source PDF is immutable and always kept) right
after the columns exist. A submission whose file is missing (already purged,
or a hand-built fixture) gets a stable, clearly-synthetic hash instead of an
empty one, so it stays loadable rather than crashing every read.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from pypdf import PdfReader

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _app_data_root(connection: sa.engine.Connection) -> Path | None:
    """The ``app-data/`` directory this database lives in, or ``None`` if the
    database isn't a plain file (e.g. ``:memory:``) -- backfill is skipped then,
    since there is nowhere a source PDF could live either."""
    database = connection.engine.url.database
    if not database or database == ":memory:":
        return None
    return Path(database).resolve().parent


def _backfill_submission_metadata(connection: sa.engine.Connection) -> None:
    root = _app_data_root(connection)
    rows = connection.execute(sa.text("SELECT id, source_pdf_path FROM submissions")).mappings()
    for row in rows:
        sha256_value: str | None = None
        page_count_value: int | None = None
        pdf_path = root / row["source_pdf_path"] if root and row["source_pdf_path"] else None
        if pdf_path is not None and pdf_path.is_file():
            data = pdf_path.read_bytes()
            sha256_value = hashlib.sha256(data).hexdigest()
            try:
                page_count_value = len(PdfReader(pdf_path).pages)
            except Exception:
                page_count_value = None
        if sha256_value is None:
            # No readable source file: synthesize a stable, non-empty hash that is
            # clearly not a real content hash, rather than leaving "" (which
            # Submission.__post_init__ rejects outright).
            sha256_value = hashlib.sha256(f"legacy-submission:{row['id']}".encode()).hexdigest()
        connection.execute(
            sa.text(
                "UPDATE submissions SET source_pdf_sha256 = :sha256, "
                "page_count = :page_count WHERE id = :id"
            ),
            {
                "sha256": sha256_value,
                "page_count": page_count_value or 1,
                "id": row["id"],
            },
        )


def upgrade() -> None:
    with op.batch_alter_table("submissions", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("source_pdf_sha256", sa.String(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("page_count", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(sa.Column("original_filename", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("review_reason", sa.String(), nullable=True))
        batch_op.create_check_constraint("ck_submissions_page_count_positive", "page_count >= 1")
        batch_op.create_index("ix_submissions_test_content_hash", ["test_id", "source_pdf_sha256"])

    _backfill_submission_metadata(op.get_bind())

    op.create_table(
        "answer_images",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.String(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("page >= 1", name="ck_answer_images_page_positive"),
        sa.CheckConstraint(
            "status IN ('ok', 'needs_review')", name="ck_answer_images_status_valid"
        ),
        sa.CheckConstraint(
            "(status = 'ok' AND reason IS NULL) OR "
            "(status = 'needs_review' AND reason IS NOT NULL AND trim(reason) != '')",
            name="ck_answer_images_reason_matches_status",
        ),
        sa.UniqueConstraint(
            "submission_id", "question_id", name="uq_answer_images_submission_question"
        ),
    )
    op.create_index("ix_answer_images_submission_id", "answer_images", ["submission_id"])


def downgrade() -> None:
    op.drop_index("ix_answer_images_submission_id", table_name="answer_images")
    op.drop_table("answer_images")

    with op.batch_alter_table("submissions", recreate="always") as batch_op:
        batch_op.drop_index("ix_submissions_test_content_hash")
        batch_op.drop_constraint("ck_submissions_page_count_positive", type_="check")
        batch_op.drop_column("review_reason")
        batch_op.drop_column("original_filename")
        batch_op.drop_column("page_count")
        batch_op.drop_column("source_pdf_sha256")
