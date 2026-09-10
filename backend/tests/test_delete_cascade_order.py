"""Deleting a row a `Review` names must not depend on ``sqlite_master`` order.

Every ``reviews`` CHECK that requires a column (``approved`` needs the AI
grade, ``modified`` the human grade, ``regrade_requested`` the job, ``undone``
the review it reverts) used to be paired with an ``ON DELETE SET NULL`` on that
very column. SET NULL rewrites the review row *while it still exists*, so
removing the row it names aborts the whole delete on that CHECK -- Issue #149.

Whether the abort happens is decided by the order SQLite walks the foreign
keys in, which is the order the tables sit in ``sqlite_master``. That order is
not a design decision anyone made: it is whatever the last migration happened
to leave behind, and any migration that rebuilds ``grade_results`` or
``reviews`` (`batch_alter_table`, the only way to add a CHECK in SQLite) moves
that table to the end and flips it. Issue #136 measured exactly that: 6 red out
of 6 with the rebuild, 8 green out of 8 without.

So these tests never assert on an order. They delete each referenced row on its
own -- no cascade to be ordered -- and they run the whole-test purge against
every table order a rebuild can produce.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, select, text

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.purge import purge_test
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.db.engine import create_sqlite_engine
from auto_scoring.db.orm import ReviewRow
from auto_scoring.domain.models import GradingSource, ReviewAction
from tests.support import (
    at,
    make_grade,
    make_job,
    make_question,
    make_review,
    make_submission,
    make_test,
)

UowFactory = Callable[[], SqlAlchemyUnitOfWork]

#: ``(table, row id, the reviews that must survive it)``. One case per action
#: whose CHECK requires a column: deleting the row that column names has to
#: stay possible, and has to take exactly the reviews that named it. Removing
#: ``review-approved`` also removes ``review-undone``, which names *it*.
_REFERENCED_ROWS = [
    pytest.param(
        "grade_results", "grade-ai", ["review-modified", "review-regrade"], id="approved-ai-grade"
    ),
    pytest.param(
        "grade_results",
        "grade-human",
        ["review-approved", "review-regrade", "review-undone"],
        id="modified-human-grade",
    ),
    pytest.param(
        "jobs",
        "job-1",
        ["review-approved", "review-modified", "review-undone"],
        id="regrade_requested-job",
    ),
    pytest.param(
        "reviews",
        "review-approved",
        ["review-modified", "review-regrade"],
        id="undone-target-review",
    ),
]


def _seed(make_uow: UowFactory) -> None:
    """A question whose review history exercises all four required columns."""
    with make_uow() as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question())
        uow.submissions.add(make_submission())
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.grades.add(make_grade(id="grade-human", source=GradingSource.HUMAN))
        uow.jobs.add(make_job(id="job-1"))
        uow.reviews.add(make_review(id="review-approved", version=1, ai_grade_result_id="grade-ai"))
        uow.reviews.add(
            make_review(
                id="review-modified",
                version=2,
                action=ReviewAction.MODIFIED,
                ai_grade_result_id=None,
                human_grade_result_id="grade-human",
            )
        )
        uow.reviews.add(
            make_review(
                id="review-regrade",
                version=3,
                action=ReviewAction.REGRADE_REQUESTED,
                ai_grade_result_id=None,
                regrade_job_id="job-1",
            )
        )
        uow.reviews.add(
            make_review(
                id="review-undone",
                version=4,
                action=ReviewAction.UNDONE,
                ai_grade_result_id=None,
                undone_review_id="review-approved",
            )
        )
        uow.commit()


def _surviving_reviews(uow: SqlAlchemyUnitOfWork) -> list[str]:
    """Every remaining review row, hydrated through the domain, id-sorted.

    Hydration is half the assertion: `Review.__post_init__` re-checks the same
    rule each CHECK holds, so a row left behind with its required column
    blanked raises here instead of quietly reading back as a decision about
    nothing. The caller compares the whole list, so "the right ones went" and
    "nothing else went" are both said.
    """
    return sorted(review.id for review in uow.reviews.history("sub-1", "q-1"))


def _recreate(db_url: str, table: str) -> None:
    """Rebuild ``table`` the way a CHECK-adding migration does.

    ``batch_alter_table`` copies the table into a new one and renames it,
    which moves it to the end of ``sqlite_master`` and so to the end of the
    cascade order -- the flip Issue #136 measured.

    Its own engine, with ``enforce_foreign_keys=False``, because that is how
    ``migrations/env.py`` runs every migration: the intermediate ``DROP TABLE``
    is an implicit ``DELETE FROM`` when enforcement is on, which would empty
    the very history this test then asks the purge about.
    """
    engine = create_sqlite_engine(db_url, enforce_foreign_keys=False)
    try:
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            with operations.batch_alter_table(table, recreate="always"):
                pass
    finally:
        engine.dispose()


def _table_order(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return [
            name
            for (name,) in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY rowid")
            )
        ]


@pytest.mark.parametrize(("table", "row_id", "survivors"), _REFERENCED_ROWS)
def test_deleting_a_row_a_review_names_removes_the_review_with_it(
    make_uow: UowFactory,
    created_schema: Engine,
    table: str,
    row_id: str,
    survivors: list[str],
) -> None:
    _seed(make_uow)
    with make_uow() as uow:
        assert len(_surviving_reviews(uow)) == 4, "the seed must be readable before it is cut down"

    # One row, no cascade above it -- so nothing here depends on a table order.
    with created_schema.begin() as connection:
        connection.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": row_id})

    with make_uow() as uow:
        assert _surviving_reviews(uow) == survivors


@pytest.mark.parametrize("recreated", [None, "grade_results", "reviews", "jobs"])
def test_purging_a_test_survives_any_table_order(
    make_uow: UowFactory,
    created_schema: Engine,
    db_url: str,
    store: LocalFileStore,
    recreated: str | None,
) -> None:
    _seed(make_uow)
    if recreated is not None:
        _recreate(db_url, recreated)
        order = _table_order(created_schema)
        assert order[-1] == recreated, "the rebuild must actually move the table last"
    with make_uow() as uow:
        assert len(_surviving_reviews(uow)) == 4, "the rebuild must carry the history over"

    with make_uow() as uow:
        purge_test(uow, store, test_id="test-1", occurred_at=at(100))

    with make_uow() as uow:
        assert uow.tests.get("test-1") is None
        assert uow.session.scalars(select(ReviewRow)).all() == []
