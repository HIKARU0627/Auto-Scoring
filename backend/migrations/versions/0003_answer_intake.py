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
used in the *first* batch pass below only cover the *shape* of those rows
(``""`` / ``1``) so the ``ADD COLUMN`` succeeds; ``Submission.__post_init__``
(``domain/models.py``) rejects an empty ``source_pdf_sha256``, so left as
``""`` those rows would fail to load the moment this revision lands.
``_backfill_submission_metadata`` recomputes the real hash and page count
from each submission's still-present ``source.pdf`` (Issue #11: the source
PDF is immutable and always kept), right after the columns exist. A
submission whose file is missing (already purged, or a hand-built fixture)
gets a stable, clearly-synthetic hash instead of an empty one, so it stays
loadable rather than crashing every read.

A *second* batch pass, after the backfill, drops those two server defaults
again and adds a ``UNIQUE(test_id, source_pdf_sha256)`` constraint:

* The defaults were only ever a migration-time device to get the ``ADD
  COLUMN`` past SQLite's NOT NULL requirement; left in place they would let a
  future raw-SQL insert (or an adapter bug) silently commit an empty hash /
  fabricated page count instead of failing loudly, so they're removed once
  every row has a real value.
* The unique constraint has to wait until *after* the backfill: adding it in
  the first pass, while every legacy row still shares the same placeholder
  ``""`` hash, would itself violate uniqueness for any test with more than
  one legacy submission.
* This still doesn't protect against two *pre-existing* submissions in the
  same test that happen to have byte-identical PDFs -- nothing enforced that
  before this revision. If that's ever true of a real database, this
  migration fails loudly rather than silently dropping the constraint or
  picking a row to keep; that's judged safer than guessing which one a human
  would have wanted removed. Resolve it by hand (decide which submission to
  purge_submission) and re-run the upgrade.

  That check (``_reject_duplicate_content_hashes``) runs *before either batch
  pass*, against hashes computed straight from each submission's still-present
  ``source.pdf`` -- the same way the backfill above computes them, just not
  written anywhere yet. Deferring the failure until the second batch pass
  tried to add the unique constraint (an earlier version of this migration
  did that) left a real trap: SQLite's batch mode recreates the table via a
  temporary ``_alembic_tmp_submissions``, and pysqlite implicitly commits
  before DDL, so a mid-batch failure can leave that temp table behind and the
  *first* batch pass's column additions already durable on disk even though
  ``alembic_version`` never advanced past ``0002`` -- "purge the duplicate and
  re-run the upgrade" would then fail immediately with "table
  _alembic_tmp_submissions already exists" instead of actually retrying.
  Checking first means a database with a genuine duplicate is left completely
  untouched by this revision -- no column added, no temp table created -- so
  the documented recovery (purge, then re-run ``upgrade``) really does start
  clean from ``0002``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

import sqlalchemy as sa
from alembic import op
from pypdf import PdfReader

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class _SubmissionContentHash(TypedDict):
    id: str
    test_id: str
    source_pdf_sha256: str
    page_count: int


def _app_data_root(connection: sa.engine.Connection) -> Path | None:
    """The ``app-data/`` directory this database lives in, or ``None`` if the
    database isn't a plain file (e.g. ``:memory:``) -- backfill is skipped then,
    since there is nowhere a source PDF could live either."""
    database = connection.engine.url.database
    if not database or database == ":memory:":
        return None
    return Path(database).resolve().parent


def _load_content_hashes(connection: sa.engine.Connection) -> list[_SubmissionContentHash]:
    """Every existing submission's would-be ``source_pdf_sha256``/``page_count``,
    computed from its still-present ``source.pdf`` -- *before* either batch
    pass below touches ``submissions``. Read once and reused both to check for
    a legacy duplicate (``_reject_duplicate_content_hashes``) and, if none is
    found, to backfill the new columns -- so the check never has to guess at
    values the backfill would compute differently.
    """
    root = _app_data_root(connection)
    rows = connection.execute(
        sa.text("SELECT id, test_id, source_pdf_path FROM submissions")
    ).mappings()
    hashes: list[_SubmissionContentHash] = []
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
        hashes.append(
            {
                "id": row["id"],
                "test_id": row["test_id"],
                "source_pdf_sha256": sha256_value,
                "page_count": page_count_value or 1,
            }
        )
    return hashes


def _reject_duplicate_content_hashes(hashes: list[_SubmissionContentHash]) -> None:
    """Raise -- before any DDL runs -- if two pre-existing submissions in the
    same test would collide on ``uq_submissions_test_content_hash`` once it's
    added below (see the module docstring for why this has to happen first).
    """
    ids_by_key: dict[tuple[str, str], list[str]] = {}
    for row in hashes:
        key = (row["test_id"], row["source_pdf_sha256"])
        ids_by_key.setdefault(key, []).append(row["id"])
    duplicates = {key: ids for key, ids in ids_by_key.items() if len(ids) > 1}
    if not duplicates:
        return
    details = "; ".join(
        f"test {test_id!r}: submissions {ids!r} share content hash {sha256!r}"
        for (test_id, sha256), ids in duplicates.items()
    )
    raise RuntimeError(
        "Revision 0003 cannot add uq_submissions_test_content_hash: pre-existing "
        f"duplicate submission content found ({details}). Nothing enforced this "
        "before this revision. Resolve by hand -- purge_submission every "
        "duplicate but one in each group -- then re-run the upgrade; no schema "
        "change has been applied yet, so it starts cleanly from revision 0002."
    )


def _backfill_submission_metadata(
    connection: sa.engine.Connection, hashes: list[_SubmissionContentHash]
) -> None:
    for row in hashes:
        connection.execute(
            sa.text(
                "UPDATE submissions SET source_pdf_sha256 = :sha256, "
                "page_count = :page_count WHERE id = :id"
            ),
            {
                "sha256": row["source_pdf_sha256"],
                "page_count": row["page_count"],
                "id": row["id"],
            },
        )


def upgrade() -> None:
    hashes = _load_content_hashes(op.get_bind())
    _reject_duplicate_content_hashes(hashes)

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

    _backfill_submission_metadata(op.get_bind(), hashes)

    with op.batch_alter_table("submissions", recreate="always") as batch_op:
        # Migration-only scaffolding, no longer needed now every row has a real
        # value -- see the module docstring.
        batch_op.alter_column(
            "source_pdf_sha256",
            existing_type=sa.String(),
            existing_nullable=False,
            server_default=None,
        )
        batch_op.alter_column(
            "page_count",
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=None,
        )
        batch_op.create_unique_constraint(
            "uq_submissions_test_content_hash", ["test_id", "source_pdf_sha256"]
        )

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
        batch_op.drop_constraint("uq_submissions_test_content_hash", type_="unique")
        batch_op.drop_constraint("ck_submissions_page_count_positive", type_="check")
        batch_op.drop_column("review_reason")
        batch_op.drop_column("original_filename")
        batch_op.drop_column("page_count")
        batch_op.drop_column("source_pdf_sha256")
