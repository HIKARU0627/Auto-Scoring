"""Repository round-trips for `DependencyGraph` against real SQLite (Issue #26)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

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
