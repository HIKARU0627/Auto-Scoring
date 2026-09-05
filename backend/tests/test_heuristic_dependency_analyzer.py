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


def test_a_question_with_no_text_at_all_is_unresolved_not_silently_independent() -> None:
    """No prompt/model-answer/rubric text means "cannot tell", not "no dependency"."""
    questions = [QuestionInfo(question_id="q1", number="問1", page=1)]
    result = _ANALYZER.analyze(questions)
    assert result.edges == ()
    assert len(result.unresolved) == 1
    assert result.unresolved[0].question_id == "q1"


def test_whitespace_only_text_is_also_treated_as_no_text() -> None:
    """A blank-but-truthy string (e.g. "   ") must not slip past the empty check."""
    questions = [
        QuestionInfo(question_id="q1", number="問1", page=1, prompt_text="   "),
        QuestionInfo(question_id="q2", number="問2", page=1, model_answer="\n\t"),
        QuestionInfo(question_id="q3", number="問3", page=1, rubric_text=" "),
    ]
    result = _ANALYZER.analyze(questions)
    assert result.edges == ()
    assert {u.question_id for u in result.unresolved} == {"q1", "q2", "q3"}


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


def test_a_bare_number_mention_without_a_signal_phrase_is_unresolved_not_an_edge() -> None:
    """A question number mentioned with no dependency-signal phrase nearby is
    ambiguous -- it must not become a candidate edge (Issue #26 review: two
    independent questions that merely both mention "問1" could otherwise
    produce a spurious 2-cycle, which fails the whole /analyze with no draft
    to review).
    """
    questions = [
        QuestionInfo(
            question_id="q1", number="問1", page=1, prompt_text="光合成について説明せよ。"
        ),
        QuestionInfo(
            question_id="q2",
            number="問2",
            page=1,
            prompt_text="問1と同じ形式で解答せよ。",  # mentions "問1", no signal phrase
        ),
    ]
    result = _ANALYZER.analyze(questions)
    assert result.edges == ()
    assert len(result.unresolved) == 1
    assert result.unresolved[0].question_id == "q2"


def test_mutual_bare_number_mentions_do_not_produce_a_cycle() -> None:
    """Two independent questions that both merely mention each other's number
    (no signal phrase either way) must not become a 2-node cycle candidate.
    """
    questions = [
        QuestionInfo(question_id="q1", number="問1", page=1, prompt_text="問2と比較して説明せよ。"),
        QuestionInfo(question_id="q2", number="問2", page=1, prompt_text="問1と比較して説明せよ。"),
    ]
    result = _ANALYZER.analyze(questions)
    assert result.edges == ()
    assert {u.question_id for u in result.unresolved} == {"q1", "q2"}


def test_question_number_match_does_not_bleed_into_a_longer_number() -> None:
    """ "問1" must not match inside "問10" -- they are different questions."""
    questions = [
        QuestionInfo(
            question_id="q1", number="問1", page=1, prompt_text="光合成について説明せよ。"
        ),
        QuestionInfo(
            question_id="q10", number="問10", page=1, prompt_text="呼吸について説明せよ。"
        ),
        QuestionInfo(
            question_id="q2",
            number="問2",
            page=1,
            prompt_text="問10の答えを踏まえて考察せよ。",
        ),
    ]
    result = _ANALYZER.analyze(questions)
    assert [(e.from_question_id, e.to_question_id) for e in result.edges] == [("q10", "q2")]


def test_overlapping_labels_resolve_to_the_longest_match() -> None:
    """ "問1" and "問1-1" both exist as question numbers; a mention of
    "問1-1" also satisfies "問1"'s digit-boundary pattern (the character
    right after "問1" is "-", not a digit). Only the longest matching label
    -- "問1-1" -- must be treated as referenced, not both (Issue #26
    review).
    """
    questions = [
        QuestionInfo(
            question_id="q1", number="問1", page=1, prompt_text="光合成について説明せよ。"
        ),
        QuestionInfo(
            question_id="q1-1", number="問1-1", page=1, prompt_text="光合成の反応式を書け。"
        ),
        QuestionInfo(
            question_id="q2",
            number="問2",
            page=1,
            prompt_text="問1-1の答えを踏まえて考察せよ。",
        ),
    ]
    result = _ANALYZER.analyze(questions)
    assert [(e.from_question_id, e.to_question_id) for e in result.edges] == [("q1-1", "q2")]
    assert result.unresolved == ()


def test_overlapping_labels_without_a_signal_phrase_report_only_the_longest() -> None:
    questions = [
        QuestionInfo(
            question_id="q1", number="問1", page=1, prompt_text="光合成について説明せよ。"
        ),
        QuestionInfo(
            question_id="q1-1", number="問1-1", page=1, prompt_text="光合成の反応式を書け。"
        ),
        QuestionInfo(
            question_id="q2",
            number="問2",
            page=1,
            prompt_text="問1-1と同じ形式で解答せよ。",  # bare mention, no signal phrase
        ),
    ]
    result = _ANALYZER.analyze(questions)
    assert result.edges == ()
    assert len(result.unresolved) == 1
    assert result.unresolved[0].question_id == "q2"
    assert "問1-1" in result.unresolved[0].reason
    assert "問1、" not in result.unresolved[0].reason  # "問1" must not also be reported


def test_a_bare_mention_and_an_unrelated_signal_in_another_field_do_not_combine() -> None:
    """A bare number mention in `prompt_text` and a dependency-signal phrase
    that independently appears in `rubric_text` (about something else
    entirely) must not be stitched together into a false edge -- the signal
    phrase was never actually modifying the reference to "問1" (Issue #26
    review). Each field's own signal-phrase check must be local to that
    field, not to the fields concatenated together.
    """
    questions = [
        QuestionInfo(
            question_id="q1", number="問1", page=1, prompt_text="光合成について説明せよ。"
        ),
        QuestionInfo(
            question_id="q2",
            number="問2",
            page=1,
            prompt_text="問1と比較して論じよ。",  # bare mention, no signal phrase here
            rubric_text="採点は答案の根拠に基づいて行うこと。",  # signal phrase, no number here
        ),
    ]
    result = _ANALYZER.analyze(questions)
    assert result.edges == ()
    assert len(result.unresolved) == 1
    assert result.unresolved[0].question_id == "q2"
    assert "問1" in result.unresolved[0].reason


def test_signal_phrase_in_the_same_field_as_the_reference_still_becomes_an_edge() -> None:
    """Sanity check alongside the above: a signal phrase genuinely modifying
    the reference (same field) must still produce an edge -- the fix must
    not over-correct into never producing edges when other fields are also
    populated.
    """
    questions = [
        QuestionInfo(
            question_id="q1", number="問1", page=1, prompt_text="光合成について説明せよ。"
        ),
        QuestionInfo(
            question_id="q2",
            number="問2",
            page=1,
            prompt_text="問1の答えを踏まえて論じよ。",  # number + signal, same field
            rubric_text="採点は答案の根拠に基づいて行うこと。",  # unrelated signal, other field
        ),
    ]
    result = _ANALYZER.analyze(questions)
    assert [(e.from_question_id, e.to_question_id) for e in result.edges] == [("q1", "q2")]
    assert result.unresolved == ()


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
