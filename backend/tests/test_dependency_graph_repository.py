"""Repository round-trips for `DependencyGraph` against real SQLite (Issue #26)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from auto_scoring.adapters import sqlalchemy_repositories
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyGraphError,
    DependencyGraphStatus,
    DependencyProvision,
)
from tests.support import at, make_question, make_test

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


def _edge(from_id: str, to_id: str) -> DependencyEdge:
    return DependencyEdge(
        from_question_id=from_id,
        to_question_id=to_id,
        provides=(DependencyProvision.RECOGNIZED_TEXT,),
        rationale=f"{from_id}の結果を{to_id}が使用",
    )


def _draft(**overrides: object) -> DependencyGraph:
    values: dict[str, object] = {
        "id": "test-1:v1",
        "test_id": "test-1",
        "version": 1,
        "question_ids": ["q-1", "q-2"],
        "edges": [_edge("q-1", "q-2")],
        "unresolved": [],
        "created_at": at(),
    }
    values.update(overrides)
    return DependencyGraph.from_candidates(**values)  # type: ignore[arg-type]


@pytest.fixture
def seeded(make_uow: UowFactory) -> UowFactory:
    with make_uow() as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-1", number="問1"))
        uow.questions.add(make_question(id="q-2", number="問2"))
        uow.commit()
    return make_uow


def test_draft_graph_round_trips(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.dependency_graphs.save(_draft())
        uow.commit()

    with seeded() as uow:
        loaded = uow.dependency_graphs.get("test-1:v1")
    assert loaded is not None
    assert loaded.status is DependencyGraphStatus.DRAFT
    assert {(e.from_question_id, e.to_question_id) for e in loaded.edges} == {("q-1", "q-2")}


def test_edge_rows_do_not_collide_when_question_ids_contain_the_separator(
    seeded: UowFactory,
) -> None:
    """`from="a:b", to="c"` and `from="a", to="b:c"` must save as two distinct
    edges even though a naive `f"{graph_id}:{from}:{to}"` synthetic id would
    join both into the identical string (Issue #26 review: the edge table's
    primary key is the composite ``(graph_id, from_question_id,
    to_question_id)``, not a separator-joined id).
    """
    edge_1 = DependencyEdge(
        from_question_id="a:b",
        to_question_id="c",
        provides=(DependencyProvision.RECOGNIZED_TEXT,),
        rationale="rationale-1",
    )
    edge_2 = DependencyEdge(
        from_question_id="a",
        to_question_id="b:c",
        provides=(DependencyProvision.RECOGNIZED_TEXT,),
        rationale="rationale-2",
    )
    graph = DependencyGraph.from_candidates(
        id="test-1:v1",
        test_id="test-1",
        version=1,
        question_ids=["a", "b", "c", "a:b", "b:c"],
        edges=[edge_1, edge_2],
        created_at=at(),
    )

    with seeded() as uow:
        uow.dependency_graphs.save(graph)
        uow.commit()

    with seeded() as uow:
        loaded = uow.dependency_graphs.get("test-1:v1")
    assert loaded is not None
    assert {(e.from_question_id, e.to_question_id) for e in loaded.edges} == {
        ("a:b", "c"),
        ("a", "b:c"),
    }


def test_saving_the_same_version_twice_replaces_the_draft_in_place(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.dependency_graphs.save(_draft(edges=[_edge("q-1", "q-2")]))
        uow.commit()

    with seeded() as uow:
        uow.dependency_graphs.save(
            _draft(edges=[], created_at=at(5))
        )  # regenerated candidates: no edges this time
        uow.commit()

    with seeded() as uow:
        loaded = uow.dependency_graphs.get("test-1:v1")
        assert loaded is not None
        assert loaded.edges == ()
        # The row's own timestamp moves with the content it now holds -- a
        # GET right after this save must not report the first save's time.
        assert loaded.created_at == at(5)
        assert len(uow.dependency_graphs.list_versions("test-1")) == 1


def test_confirming_persists_and_locks_the_version(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.dependency_graphs.save(_draft())
        uow.commit()

    with seeded() as uow:
        draft = uow.dependency_graphs.get("test-1:v1")
        assert draft is not None
        confirmed = draft.confirm(edges=[_edge("q-1", "q-2")], confirmed_at=at(10))
        uow.dependency_graphs.save(confirmed)
        uow.commit()

    with seeded() as uow:
        loaded = uow.dependency_graphs.get("test-1:v1")
        assert loaded is not None
        assert loaded.status is DependencyGraphStatus.CONFIRMED

        # A confirmed version can never be overwritten again.
        with pytest.raises(DependencyGraphError):
            uow.dependency_graphs.save(_draft(edges=[]))


def test_save_reports_a_conflict_when_confirmation_races_ahead_of_a_draft_overwrite(
    seeded: UowFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`save()`'s early "is it CONFIRMED?" check only proves the row was
    DRAFT *when this call read it*; it says nothing about whether another
    transaction confirms the row afterwards but before this call's own
    write executes. Without an atomic ``WHERE status = 'draft'`` on the
    actual UPDATE, this call would still delete the confirmed edges and
    write its own (stale, pre-confirm) status back over CONFIRMED --
    silently un-confirming a graph a human already signed off on (Issue #26
    review). Injects the concurrent confirm directly between `save()`'s read
    and its atomic write via a monkeypatch on `update`, the same technique
    used for the other CAS races in this codebase.
    """
    with seeded() as uow:
        uow.dependency_graphs.save(_draft())
        uow.commit()

    with seeded() as reader_uow:
        stale_draft = reader_uow.dependency_graphs.get("test-1:v1")
        assert stale_draft is not None

        injected = {"done": False}

        def _confirm_concurrently_then_update(table: Any) -> Any:
            if not injected["done"]:
                injected["done"] = True
                with seeded() as confirming_uow:
                    to_confirm = confirming_uow.dependency_graphs.get("test-1:v1")
                    assert to_confirm is not None
                    confirmed = to_confirm.confirm(edges=[_edge("q-1", "q-2")], confirmed_at=at(5))
                    assert confirming_uow.dependency_graphs.try_confirm(confirmed) is True
                    confirming_uow.commit()
            return update(table)

        monkeypatch.setattr(sqlalchemy_repositories, "update", _confirm_concurrently_then_update)

        regenerated = _draft(edges=[], created_at=at(10))  # as if /analyze re-ran
        with pytest.raises(DependencyGraphError):
            reader_uow.dependency_graphs.save(regenerated)

    with seeded() as uow:
        stored = uow.dependency_graphs.get("test-1:v1")
    assert stored is not None
    assert stored.status is DependencyGraphStatus.CONFIRMED
    assert {(e.from_question_id, e.to_question_id) for e in stored.edges} == {("q-1", "q-2")}


def test_try_confirm_lets_only_one_racing_confirm_win(seeded: UowFactory) -> None:
    """Two reviewers who both read the same DRAFT before either wrote must
    not both succeed -- the second's `try_confirm` must lose cleanly, and the
    persisted edges must be exactly the winner's (Issue #26 review: atomic
    confirm).
    """
    with seeded() as uow:
        uow.dependency_graphs.save(_draft())
        uow.commit()

    with seeded() as uow:
        draft = uow.dependency_graphs.get("test-1:v1")
        assert draft is not None
        # Both built from the *same* stale DRAFT read, like two concurrent
        # reviewers who each fetched it before either confirmed.
        confirmed_a = draft.confirm(edges=[_edge("q-1", "q-2")], confirmed_at=at(5))
        confirmed_b = draft.confirm(edges=[], confirmed_at=at(6))

        assert uow.dependency_graphs.try_confirm(confirmed_a) is True
        assert uow.dependency_graphs.try_confirm(confirmed_b) is False
        uow.commit()

    with seeded() as uow:
        stored = uow.dependency_graphs.get("test-1:v1")
    assert stored is not None
    assert stored.status is DependencyGraphStatus.CONFIRMED
    assert stored.confirmed_at == at(5)
    assert {(e.from_question_id, e.to_question_id) for e in stored.edges} == {("q-1", "q-2")}


def test_try_confirm_rejects_an_already_confirmed_row(seeded: UowFactory) -> None:
    with seeded() as uow:
        draft = _draft()
        uow.dependency_graphs.save(draft)
        confirmed = draft.confirm(edges=[_edge("q-1", "q-2")], confirmed_at=at(5))
        assert uow.dependency_graphs.try_confirm(confirmed) is True
        uow.commit()

    with seeded() as uow:
        # A second, independent confirm attempt against the same (now
        # CONFIRMED) version must also lose, not raise or silently repeat.
        stale = _draft()
        confirmed_again = stale.confirm(edges=[], confirmed_at=at(6))
        assert uow.dependency_graphs.try_confirm(confirmed_again) is False


def test_try_confirm_rejects_when_a_newer_version_is_already_confirmed(
    seeded: UowFactory,
) -> None:
    with seeded() as uow:
        uow.dependency_graphs.save(_draft())
        uow.dependency_graphs.save(_draft(id="test-1:v2", version=2, edges=[]))
        uow.commit()

    with seeded() as uow:
        v2 = uow.dependency_graphs.get("test-1:v2")
        assert v2 is not None
        confirmed_v2 = v2.confirm(edges=[], confirmed_at=at(5))
        assert uow.dependency_graphs.try_confirm(confirmed_v2) is True
        uow.commit()

    with seeded() as uow:
        v1 = uow.dependency_graphs.get("test-1:v1")
        assert v1 is not None
        confirmed_v1 = v1.confirm(edges=[], confirmed_at=at(6))
        assert uow.dependency_graphs.try_confirm(confirmed_v1) is False

    with seeded() as uow:
        stored_v1 = uow.dependency_graphs.get("test-1:v1")
    assert stored_v1 is not None
    assert stored_v1.status is DependencyGraphStatus.DRAFT


def test_try_confirm_rejects_when_the_question_set_changed_since_the_snapshot(
    seeded: UowFactory,
) -> None:
    """A question added after the graph was read (but before the atomic
    write) must not let a stale question-set snapshot get CONFIRMED (Issue
    #26 review: the check must be evaluated at write time, not read time).
    """
    with seeded() as uow:
        uow.dependency_graphs.save(_draft())
        uow.commit()

    with seeded() as uow:
        draft = uow.dependency_graphs.get("test-1:v1")
        assert draft is not None
        confirmed = draft.confirm(edges=[_edge("q-1", "q-2")], confirmed_at=at(5))

        # As if a concurrent request added a question for this test in the
        # window between this request's own read and its write.
        uow.questions.add(make_question(id="q-3", number="問3"))

        assert uow.dependency_graphs.try_confirm(confirmed) is False
        uow.commit()

    with seeded() as uow:
        stored = uow.dependency_graphs.get("test-1:v1")
    assert stored is not None
    assert stored.status is DependencyGraphStatus.DRAFT


def test_get_latest_returns_the_highest_version(seeded: UowFactory) -> None:
    with seeded() as uow:
        v1 = _draft()
        uow.dependency_graphs.save(v1)
        uow.dependency_graphs.save(v1.confirm(edges=[_edge("q-1", "q-2")], confirmed_at=at(5)))
        uow.commit()

    with seeded() as uow:
        uow.dependency_graphs.save(_draft(id="test-1:v2", version=2, edges=[]))
        uow.commit()

    with seeded() as uow:
        latest = uow.dependency_graphs.get_latest("test-1")
    assert latest is not None
    assert latest.version == 2
    assert latest.status is DependencyGraphStatus.DRAFT


def test_list_versions_returns_every_version_in_order(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.dependency_graphs.save(_draft())
        uow.dependency_graphs.save(_draft(id="test-1:v2", version=2, edges=[]))
        uow.commit()

    with seeded() as uow:
        versions = uow.dependency_graphs.list_versions("test-1")
    assert [g.version for g in versions] == [1, 2]


def test_get_latest_with_no_graph_returns_none(seeded: UowFactory) -> None:
    with seeded() as uow:
        assert uow.dependency_graphs.get_latest("test-1") is None


def test_unknown_test_id_is_rejected_by_foreign_key(make_uow: UowFactory) -> None:
    with make_uow() as uow, pytest.raises(Exception):  # noqa: B017 - IntegrityError from SQLite FK
        uow.dependency_graphs.save(_draft(test_id="missing-test", id="missing-test:v1"))
        uow.commit()


def test_confirmed_status_without_confirmed_at_is_rejected_by_check_constraint(
    seeded: UowFactory,
) -> None:
    """`DependencyGraph.__post_init__` requires CONFIRMED <=> confirmed_at is
    set; a row bypassing the domain (repair, import, direct SQL) must not be
    able to violate that pairing, or `_hydrate` would raise
    `DependencyGraphError` on every later GET/list of it (Issue #26 review).
    """
    from auto_scoring.db.orm import DependencyGraphRow

    with pytest.raises(IntegrityError), seeded() as uow:
        uow.session.add(
            DependencyGraphRow(
                id="test-1:v1",
                test_id="test-1",
                version=1,
                status=DependencyGraphStatus.CONFIRMED,
                question_ids=["q-1", "q-2"],
                unresolved=[],
                created_at=at(),
                confirmed_at=None,
            )
        )
        uow.commit()


def test_draft_status_with_confirmed_at_is_rejected_by_check_constraint(
    seeded: UowFactory,
) -> None:
    from auto_scoring.db.orm import DependencyGraphRow

    with pytest.raises(IntegrityError), seeded() as uow:
        uow.session.add(
            DependencyGraphRow(
                id="test-1:v1",
                test_id="test-1",
                version=1,
                status=DependencyGraphStatus.DRAFT,
                question_ids=["q-1", "q-2"],
                unresolved=[],
                created_at=at(),
                confirmed_at=at(5),
            )
        )
        uow.commit()
