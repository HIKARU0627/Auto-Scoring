"""Unit tests for the offline reference-based dependency analyzer (Issue #26)."""

from __future__ import annotations

from auto_scoring.adapters.heuristic_dependency_analyzer import ReferenceHeuristicDependencyAnalyzer
from auto_scoring.domain.dependency_analysis import QuestionInfo

_ANALYZER = ReferenceHeuristicDependencyAnalyzer()


def test_independent_questions_produce_no_edges_or_unresolved() -> None:
    questions = [
        QuestionInfo(
            question_id="q1", number="問1", page=1, prompt_text="光合成について説明せよ。"
        ),
        QuestionInfo(question_id="q2", number="問2", page=1, prompt_text="呼吸について説明せよ。"),
    ]
    result = _ANALYZER.analyze(questions)
    assert result.edges == ()
    assert result.unresolved == ()


def test_explicit_reference_with_signal_phrase_becomes_a_high_confidence_edge() -> None:
    questions = [
        QuestionInfo(
            question_id="q1", number="問1", page=1, prompt_text="光合成の仕組みを説明せよ。"
        ),
        QuestionInfo(
            question_id="q2",
            number="問2",
            page=1,
            prompt_text="問1の答えを踏まえて、呼吸との違いを説明せよ。",
        ),
    ]
    result = _ANALYZER.analyze(questions)
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert (edge.from_question_id, edge.to_question_id) == ("q1", "q2")
    assert edge.confidence == 0.8
    assert result.unresolved == ()


def test_signal_phrase_without_a_resolvable_reference_is_unresolved_not_dropped() -> None:
    questions = [
        QuestionInfo(
            question_id="q1", number="問1", page=1, prompt_text="光合成について説明せよ。"
        ),
        QuestionInfo(
            question_id="q2",
            number="問2",
            page=2,
            prompt_text="前の設問の結果を用いて考察せよ。",
        ),
    ]
    result = _ANALYZER.analyze(questions)
    assert result.edges == ()
    assert len(result.unresolved) == 1
    assert result.unresolved[0].question_id == "q2"


def test_multi_page_reference_is_detected() -> None:
    questions = [
        QuestionInfo(
            question_id="p1q1", number="問1", page=1, prompt_text="下線部の意味を答えよ。"
        ),
        QuestionInfo(
            question_id="p2q2",
            number="問2",
            page=2,
            prompt_text="問1の答えに基づいて英作文せよ。",
        ),
    ]
    result = _ANALYZER.analyze(questions)
    assert [(e.from_question_id, e.to_question_id) for e in result.edges] == [("p1q1", "p2q2")]
