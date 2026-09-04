"""Unit tests for the dependency-graph domain model (Issue #26).

Covers the acceptance criteria directly: independent/serial/branch-merge
fixtures produce the right DAG and parallel layers; self-loop/unknown
id/cycle/duplicate edges are all rejected with the offending ids named;
confirm() is the only path to CONFIRMED and locks the version afterwards;
`can_start_submission_processing` gates on that status.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import pytest

from auto_scoring.domain.dependency_graph import (
    CycleDetectedError,
    DependencyEdge,
    DependencyGraph,
    DependencyGraphError,
    DependencyGraphStatus,
    DependencyProvision,
    DuplicateEdgeError,
    SelfLoopError,
    UnknownQuestionError,
    UnresolvedQuestion,
    can_start_submission_processing,
)

CREATED_AT = datetime(2026, 1, 1)
CONFIRMED_AT = datetime(2026, 1, 2)


def _edge(from_id: str, to_id: str, **overrides: object) -> DependencyEdge:
    values: dict[str, object] = {
        "from_question_id": from_id,
        "to_question_id": to_id,
        "provides": (DependencyProvision.RECOGNIZED_TEXT,),
        "rationale": f"{from_id}の結果を{to_id}が使用",
    }
    values.update(overrides)
    return DependencyEdge(**values)  # type: ignore[arg-type]


def _draft(
    question_ids: list[str],
    edges: Sequence[DependencyEdge] = (),
    unresolved: Sequence[UnresolvedQuestion] = (),
) -> DependencyGraph:
    return DependencyGraph.from_candidates(
        id="dg-1",
        test_id="test-1",
        version=1,
        question_ids=question_ids,
        edges=edges,
        unresolved=unresolved,
        created_at=CREATED_AT,
    )


# --------------------------------------------------------------------------- #
# Fixture-driven DAG / layer generation
# --------------------------------------------------------------------------- #
def test_all_independent_questions_land_in_one_layer() -> None:
    graph = _draft(["q1", "q2", "q3"])
    assert graph.topological_layers() == (("q1", "q2", "q3"),)


def test_fully_serial_chain_produces_one_question_per_layer() -> None:
    graph = _draft(["q1", "q2", "q3"], edges=[_edge("q1", "q2"), _edge("q2", "q3")])
    assert graph.topological_layers() == (("q1",), ("q2",), ("q3",))


def test_branch_and_merge_layers_correctly() -> None:
    # q1 -> q2, q1 -> q3, {q2, q3} -> q4
    graph = _draft(
        ["q1", "q2", "q3", "q4"],
        edges=[_edge("q1", "q2"), _edge("q1", "q3"), _edge("q2", "q4"), _edge("q3", "q4")],
    )
    assert graph.topological_layers() == (("q1",), ("q2", "q3"), ("q4",))


def test_multi_page_dependency_is_representable() -> None:
    # Page 1 question 1 feeds page 2 question 2.
    edge = _edge("p1q1", "p2q2", rationale="Page1問1の結果をPage2問2で使用")
    graph = _draft(["p1q1", "p2q2"], edges=[edge])
    assert graph.topological_layers() == (("p1q1",), ("p2q2",))


# --------------------------------------------------------------------------- #
# Rejections: self-loop / unknown id / cycle / duplicate edge
# --------------------------------------------------------------------------- #
def test_self_loop_is_rejected_with_question_id() -> None:
    with pytest.raises(SelfLoopError) as excinfo:
        _edge("q1", "q1")
    assert excinfo.value.question_id == "q1"


def test_unknown_question_id_in_edge_is_rejected() -> None:
    with pytest.raises(UnknownQuestionError) as excinfo:
        _draft(["q1", "q2"], edges=[_edge("q1", "q-missing")])
    assert "q-missing" in excinfo.value.question_ids


def test_unknown_question_id_in_unresolved_is_rejected() -> None:
    with pytest.raises(UnknownQuestionError):
        _draft(["q1"], unresolved=[UnresolvedQuestion(question_id="q-missing", reason="不明")])


def test_cycle_is_rejected_and_names_the_offending_questions() -> None:
    with pytest.raises(CycleDetectedError) as excinfo:
        _draft(["q1", "q2", "q3"], edges=[_edge("q1", "q2"), _edge("q2", "q3"), _edge("q3", "q1")])
    assert set(excinfo.value.cycle_question_ids) == {"q1", "q2", "q3"}


def test_cycle_report_excludes_nodes_merely_downstream_of_it() -> None:
    """q1 <-> q2 is the cycle; q3 only depends on q2 and is not part of it."""
    with pytest.raises(CycleDetectedError) as excinfo:
        _draft(
            ["q1", "q2", "q3"],
            edges=[_edge("q1", "q2"), _edge("q2", "q1"), _edge("q2", "q3")],
        )
    assert set(excinfo.value.cycle_question_ids) == {"q1", "q2"}


def test_duplicate_edge_is_rejected() -> None:
    with pytest.raises(DuplicateEdgeError) as excinfo:
        _draft(["q1", "q2"], edges=[_edge("q1", "q2"), _edge("q1", "q2", rationale="別の根拠")])
    assert excinfo.value.pairs == (("q1", "q2"),)


def test_edge_requires_non_empty_rationale() -> None:
    with pytest.raises(DependencyGraphError):
        _edge("q1", "q2", rationale="   ")


def test_edge_confidence_must_be_within_unit_range() -> None:
    with pytest.raises(DependencyGraphError):
        _edge("q1", "q2", confidence=1.5)


# --------------------------------------------------------------------------- #
# Draft -> confirm lifecycle and version immutability
# --------------------------------------------------------------------------- #
def test_candidates_are_always_saved_as_draft() -> None:
    graph = _draft(["q1", "q2"], edges=[_edge("q1", "q2")])
    assert graph.status is DependencyGraphStatus.DRAFT
    assert graph.confirmed_at is None


def test_confirm_replaces_candidates_and_clears_unresolved() -> None:
    draft = _draft(
        ["q1", "q2", "q3"],
        edges=[_edge("q1", "q2")],
        unresolved=[UnresolvedQuestion(question_id="q3", reason="根拠不足")],
    )
    confirmed = draft.confirm(
        edges=[_edge("q1", "q2"), _edge("q1", "q3")], confirmed_at=CONFIRMED_AT
    )
    assert confirmed.status is DependencyGraphStatus.CONFIRMED
    assert confirmed.unresolved == ()
    assert confirmed.confirmed_at == CONFIRMED_AT
    confirmed_pairs = {(e.from_question_id, e.to_question_id) for e in confirmed.edges}
    assert confirmed_pairs == {("q1", "q2"), ("q1", "q3")}
    # the version stays the same -- confirming does not bump it (Issue #26 doc).
    assert confirmed.version == draft.version


def test_confirming_an_already_confirmed_graph_is_rejected() -> None:
    draft = _draft(["q1", "q2"], edges=[_edge("q1", "q2")])
    confirmed = draft.confirm(edges=[_edge("q1", "q2")], confirmed_at=CONFIRMED_AT)
    with pytest.raises(DependencyGraphError):
        confirmed.confirm(edges=[_edge("q1", "q2")], confirmed_at=CONFIRMED_AT)


def test_confirmed_graph_that_still_has_a_cycle_is_rejected() -> None:
    draft = _draft(["q1", "q2"])
    with pytest.raises(CycleDetectedError):
        draft.confirm(edges=[_edge("q1", "q2"), _edge("q2", "q1")], confirmed_at=CONFIRMED_AT)


def test_confirmed_graph_cannot_carry_unresolved_questions() -> None:
    """Even built directly (not via `confirm`), CONFIRMED + unresolved is invalid.

    `confirm()` itself always clears `unresolved`, so this guards the
    constructor/`from_dict` path against a corrupted or hand-built row that
    would let `can_start_submission_processing` see a CONFIRMED graph whose
    ambiguity was never actually resolved.
    """
    with pytest.raises(DependencyGraphError):
        DependencyGraph(
            id="dg-1",
            test_id="test-1",
            version=1,
            question_ids=frozenset({"q1", "q2"}),
            edges=(),
            unresolved=(UnresolvedQuestion(question_id="q2", reason="根拠不足"),),
            status=DependencyGraphStatus.CONFIRMED,
            created_at=CREATED_AT,
            confirmed_at=CONFIRMED_AT,
        )


# --------------------------------------------------------------------------- #
# Submission-processing gate
# --------------------------------------------------------------------------- #
def test_processing_is_blocked_without_a_graph() -> None:
    assert can_start_submission_processing(None) is False


def test_processing_is_blocked_while_draft() -> None:
    assert can_start_submission_processing(_draft(["q1"])) is False


def test_processing_is_allowed_once_confirmed() -> None:
    draft = _draft(["q1"])
    confirmed = draft.confirm(edges=[], confirmed_at=CONFIRMED_AT)
    assert can_start_submission_processing(confirmed) is True


# --------------------------------------------------------------------------- #
# Serialization round-trip
# --------------------------------------------------------------------------- #
def test_to_dict_from_dict_round_trip() -> None:
    draft = _draft(
        ["q1", "q2"],
        edges=[_edge("q1", "q2", confidence=0.7)],
        unresolved=[UnresolvedQuestion(question_id="q2", reason="根拠不足")],
    )
    restored = DependencyGraph.from_dict(draft.to_dict())
    assert restored == draft
