"""`auto_scoring.domain.grading_context`: prerequisite-context assembly
(Issue #20; business-rules-and-evaluation-data.md section 4.3).
"""

from __future__ import annotations

import pytest

from auto_scoring.domain.ai_provider import PrerequisiteAnswer
from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyProvision,
)
from auto_scoring.domain.grading_context import (
    MissingPrerequisiteContextError,
    PrerequisiteSource,
    build_context_entries,
    build_prerequisite_context,
)
from auto_scoring.domain.models import CriterionOutcome, CriterionResult
from tests.support import at, make_grade, make_recognition

_CREATED_AT = at()


def _graph(edges: list[DependencyEdge]) -> DependencyGraph:
    question_ids = (
        {"q-1", "q-2"} | {e.from_question_id for e in edges} | {e.to_question_id for e in edges}
    )
    return DependencyGraph.from_candidates(
        id="g-1",
        test_id="test-1",
        version=1,
        question_ids=sorted(question_ids),
        edges=edges,
        created_at=_CREATED_AT,
    )


def test_no_prerequisite_edges_yields_an_empty_context() -> None:
    graph = _graph([])
    assert build_prerequisite_context(graph, "q-2", sources={}) == ()
    assert build_context_entries(graph, "q-2", sources={}) == ()


def test_recognized_text_provision_is_carried_through() -> None:
    edge = DependencyEdge(
        from_question_id="q-1",
        to_question_id="q-2",
        provides=(DependencyProvision.RECOGNIZED_TEXT,),
        rationale="q2は q1の答えを使う",
    )
    graph = _graph([edge])
    recognition = make_recognition(id="rec-1", question_id="q-1", text="光合成")
    sources = {"q-1": PrerequisiteSource(recognition=recognition)}

    context = build_prerequisite_context(graph, "q-2", sources=sources)

    assert context == (
        PrerequisiteAnswer(
            question_id="q-1",
            provides=(DependencyProvision.RECOGNIZED_TEXT,),
            recognized_text="光合成",
        ),
    )
    entries = build_context_entries(graph, "q-2", sources=sources)
    assert entries[0].question_id == "q-1"
    assert entries[0].recognition_result_id == "rec-1"
    assert entries[0].grade_result_id is None


def test_score_and_criterion_provisions_are_carried_through() -> None:
    edge = DependencyEdge(
        from_question_id="q-1",
        to_question_id="q-2",
        provides=(DependencyProvision.SCORE, DependencyProvision.CRITERION_RESULT),
        rationale="q2の配点は q1の結果で変わる",
    )
    graph = _graph([edge])
    grade = make_grade(
        id="grade-1",
        question_id="q-1",
        criteria=(CriterionResult(criterion_id="c-1", outcome=CriterionOutcome.PASS),),
    )
    sources = {"q-1": PrerequisiteSource(grade=grade)}

    context = build_prerequisite_context(graph, "q-2", sources=sources)

    assert len(context) == 1
    answer = context[0]
    assert answer.score == grade.score.awarded
    assert answer.max_score == grade.score.maximum
    assert answer.criteria == grade.criteria
    entries = build_context_entries(graph, "q-2", sources=sources)
    assert entries[0].grade_result_id == "grade-1"


def test_missing_recognized_text_raises_instead_of_fabricating() -> None:
    edge = DependencyEdge(
        from_question_id="q-1",
        to_question_id="q-2",
        provides=(DependencyProvision.RECOGNIZED_TEXT,),
        rationale="根拠",
    )
    graph = _graph([edge])

    with pytest.raises(MissingPrerequisiteContextError):
        build_prerequisite_context(graph, "q-2", sources={})


def test_missing_score_raises_instead_of_fabricating() -> None:
    edge = DependencyEdge(
        from_question_id="q-1",
        to_question_id="q-2",
        provides=(DependencyProvision.SCORE,),
        rationale="根拠",
    )
    graph = _graph([edge])
    # A recognition exists, but no grade -- SCORE still cannot be answered.
    sources = {"q-1": PrerequisiteSource(recognition=make_recognition(question_id="q-1"))}

    with pytest.raises(MissingPrerequisiteContextError):
        build_prerequisite_context(graph, "q-2", sources=sources)


def test_a_question_outside_the_graph_edges_never_appears() -> None:
    """business-rules-and-evaluation-data.md section 4.3: "依存関係が確定
    DAGに無い設問の情報" must never cross into the context, even if a
    ``sources`` mapping happens to carry it (e.g. leftover from a caller
    that queried more broadly than necessary)."""
    edge = DependencyEdge(
        from_question_id="q-1",
        to_question_id="q-2",
        provides=(DependencyProvision.RECOGNIZED_TEXT,),
        rationale="根拠",
    )
    graph = _graph([edge])
    sources = {
        "q-1": PrerequisiteSource(recognition=make_recognition(question_id="q-1")),
        "q-unrelated": PrerequisiteSource(recognition=make_recognition(question_id="q-unrelated")),
    }

    context = build_prerequisite_context(graph, "q-2", sources=sources)

    assert {answer.question_id for answer in context} == {"q-1"}


def test_human_recognition_preferred_over_ai_by_the_caller_is_carried_through() -> None:
    """This module trusts whatever ``sources`` already resolved -- it is the
    caller's job (Issue #20's `GradingJobProcessor`) to prefer a human
    confirmation, not this pure assembly step's."""
    edge = DependencyEdge(
        from_question_id="q-1",
        to_question_id="q-2",
        provides=(DependencyProvision.RECOGNIZED_TEXT,),
        rationale="根拠",
    )
    graph = _graph([edge])
    human_recognition = make_recognition(
        id="rec-human", question_id="q-1", text="人間による修正", created_at=at(1)
    )
    sources = {"q-1": PrerequisiteSource(recognition=human_recognition)}

    context = build_prerequisite_context(graph, "q-2", sources=sources)

    assert context[0].recognized_text == "人間による修正"
