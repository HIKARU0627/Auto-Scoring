"""A deterministic, offline `DependencyAnalyzer` (Issue #26).

No `AIProvider`/OCR call is wired here: the concrete AI service is still
PoC-pending (docs/technology-stack.md §3.5), so this adapter looks for
explicit cross-question references in a question's own text -- "問1を踏まえて"
style phrasing -- which is enough to exercise the analyze -> draft -> human
review -> confirm -> version pipeline end to end without an external call.
It is registered behind `DependencyAnalyzer` precisely so a future
AIProvider-backed analyzer can replace it without touching callers. See
docs/dependency-graph.md "候補生成: ヒューリスティック analyzer" for the recorded
decision and its limits.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from auto_scoring.domain.dependency_analysis import DependencyAnalysisResult, QuestionInfo
from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyProvision,
    UnresolvedQuestion,
)

_SIGNAL_PHRASES = (
    "を踏まえて",
    "を踏まえ",
    "の結果を用いて",
    "の結果を使って",
    "を参照",
    "に基づいて",
    "に基づき",
)


@dataclass(frozen=True)
class ReferenceHeuristicDependencyAnalyzer:
    """Flags `to` as depending on `from` when `to`'s own text mentions `from`'s
    question number. A nearby dependency-signal phrase raises confidence; a
    signal phrase with no resolvable question number becomes `unresolved`
    rather than a guess.
    """

    def analyze(self, questions: Sequence[QuestionInfo]) -> DependencyAnalysisResult:
        by_number = {question.number: question.question_id for question in questions}
        edges: list[DependencyEdge] = []
        unresolved: list[UnresolvedQuestion] = []

        for question in questions:
            # `.strip()` before the truthiness check: a whitespace-only part
            # (e.g. an override of "   ") is truthy as a plain string and
            # would otherwise slip past `if part` and make `text` itself
            # falsely non-empty after the join.
            fields = [
                part.strip()
                for part in (question.prompt_text, question.model_answer, question.rubric_text)
                if part and part.strip()
            ]
            text = " ".join(fields)
            if not text:
                # No prompt/model-answer/rubric text to analyze at all. This
                # is not "no dependency" -- it is "cannot tell" -- so it must
                # surface as unresolved, or a human could confirm an
                # unreviewed "independent" verdict that was never actually
                # analyzed (Issue #26: 分析不能を「依存なし」と推測しない).
                unresolved.append(
                    UnresolvedQuestion(
                        question_id=question.question_id,
                        reason="問題文/模範解答/採点基準のテキストが無く、依存関係を分析できません",
                    )
                )
                continue

            matched_signal = next((phrase for phrase in _SIGNAL_PHRASES if phrase in text), None)
            referenced_pairs = [
                (number, from_id)
                for number, from_id, _ in _resolve_referenced_numbers(
                    text, by_number, question.question_id
                )
            ]

            # A question number and a dependency-signal phrase must appear
            # together in the *same* source field (prompt/model-answer/
            # rubric) to become an edge -- not merely somewhere each in the
            # combined text. Without this, a bare label mention in one field
            # (e.g. prompt: "問1と比較する") and an unrelated signal phrase
            # in another (e.g. rubric: "根拠に基づいて採点する") would each
            # make their own field-wide check true, and the two independent,
            # unrelated statements would be stitched into a false edge that
            # the signal phrase was never actually modifying (Issue #26
            # review).
            locally_referenced: list[tuple[str, str]] = []
            # (number, from_id) -> the exact field text + match span that
            # justified it, so the rationale snippet below is built from
            # *that* occurrence, not by re-searching the whole concatenated
            # `text` for the number (which could resurface a different,
            # unrelated occurrence from an earlier field -- e.g. "問1-1" in
            # `prompt_text` also satisfies "問1"'s pattern, so re-searching
            # `text` for "問1" could return a snippet about 問1-1 instead of
            # the real, signalled 問1 reference found in `rubric_text`;
            # Issue #26 review).
            local_evidence: dict[tuple[str, str], tuple[str, tuple[int, int]]] = {}
            for field in fields:
                if not any(phrase in field for phrase in _SIGNAL_PHRASES):
                    continue
                for number, from_id, span in _resolve_referenced_numbers(
                    field, by_number, question.question_id
                ):
                    pair = (number, from_id)
                    if pair not in locally_referenced:
                        locally_referenced.append(pair)
                        local_evidence[pair] = (field, span)

            if locally_referenced:
                # A question number *and* a dependency-signal phrase both
                # present in the same field: this is the only case that
                # becomes an edge. A bare label mention with no such phrase
                # is common between genuinely independent questions (e.g.
                # both discuss "問1" for unrelated reasons) and must not be
                # promoted to a candidate edge -- doing so risked handing
                # `from_candidates` a spurious cycle, which raises before any
                # draft is saved and leaves nothing for a human to
                # review/fix (Issue #26 review; docs/dependency-graph.md
                # "候補生成").
                for number, from_id in locally_referenced:
                    field_text, span = local_evidence[(number, from_id)]
                    edges.append(
                        DependencyEdge(
                            from_question_id=from_id,
                            to_question_id=question.question_id,
                            provides=(
                                DependencyProvision.RECOGNIZED_TEXT,
                                DependencyProvision.SCORE,
                            ),
                            rationale=(
                                f"{question.number}の設問文/模範解答/採点基準に"
                                f"{number}への参照表現「{_snippet_from_span(field_text, span)}」"
                                "を検出"
                            ),
                            confidence=0.8,
                        )
                    )

                # `referenced_pairs` (computed on the combined text) can name
                # numbers beyond the ones just turned into edges -- e.g. a
                # signalled reference to 問1 in `prompt_text` and a separate,
                # unsignalled bare mention of 問2 in `rubric_text`. Finding
                # an edge for 問1 must not silence 問2's ambiguity; it would
                # otherwise let a graph with an unreviewed possible
                # dependency go straight to confirm with no `unresolved`
                # entry to flag it (Issue #26 review).
                unmatched = [pair for pair in referenced_pairs if pair not in locally_referenced]
                if unmatched:
                    numbers = "、".join(number for number, _ in unmatched)
                    unresolved.append(
                        UnresolvedQuestion(
                            question_id=question.question_id,
                            reason=(
                                f"{numbers}への言及はありますが、依存を示唆する表現が見つからず、"
                                "実際に依存があるか判断できません"
                            ),
                        )
                    )
            elif referenced_pairs:
                # Number(s) mentioned but no dependency-signal phrase: could
                # be a real dependency stated plainly, or just an unrelated
                # mention -- ambiguous either way, so it goes to `unresolved`
                # rather than being silently dropped or guessed as an edge.
                numbers = "、".join(number for number, _ in referenced_pairs)
                unresolved.append(
                    UnresolvedQuestion(
                        question_id=question.question_id,
                        reason=(
                            f"{numbers}への言及はありますが、依存を示唆する表現が見つからず、"
                            "実際に依存があるか判断できません"
                        ),
                    )
                )
            elif matched_signal:
                unresolved.append(
                    UnresolvedQuestion(
                        question_id=question.question_id,
                        reason=(
                            "依存を示唆する表現を検出しましたが、参照先の設問番号を特定できません: "
                            f"「{_snippet(text, matched_signal)}」"
                        ),
                    )
                )

        return DependencyAnalysisResult(edges=tuple(edges), unresolved=tuple(unresolved))


def _question_number_pattern(number: str) -> re.Pattern[str]:
    """Match `number` as a whole label, not as a substring of a longer one.

    Without digit-boundary checks, "問1" would also match inside "問10" --
    a real risk since question numbers are themselves digit strings.
    """
    return re.compile(rf"(?<!\d){re.escape(number)}(?!\d)")


def _resolve_referenced_numbers(
    text: str, by_number: dict[str, str], exclude_id: str
) -> list[tuple[str, str, tuple[int, int]]]:
    """Which known question numbers `text` genuinely references, and where.

    Question numbers are arbitrary non-empty labels, so one can be a
    substring of another with only a non-digit separator between them --
    e.g. "問1" and "問1-1". Both patterns match inside "...問1-1を参照..."
    ("問1"'s digit-boundary lookahead is satisfied by the following "-"), so
    naively checking each label independently would report the text as
    referencing *both* "問1" and "問1-1" from a single mention of "問1-1"
    (Issue #26 review). A shorter label's match is only a genuine reference
    if it is not itself contained inside a longer label's match at the same
    position; a match fully swallowed by a longer label's span is resolved
    to that longer label instead.

    Returns the first genuine (non-absorbed) match span alongside each
    number/question-id pair, so a caller building a rationale snippet can
    slice it directly from *this* text instead of re-searching a different,
    larger text where an unrelated occurrence of the same pattern could sit
    earlier (Issue #26 review).
    """
    spans_by_number = {
        number: [match.span() for match in _question_number_pattern(number).finditer(text)]
        for number in by_number
    }

    def _is_absorbed_by_a_longer_label(number: str, span: tuple[int, int]) -> bool:
        start, end = span
        return any(
            other_start <= start and end <= other_end
            for other_number, other_spans in spans_by_number.items()
            if len(other_number) > len(number)
            for other_start, other_end in other_spans
        )

    referenced: list[tuple[str, str, tuple[int, int]]] = []
    for number, from_id in by_number.items():
        if from_id == exclude_id:
            continue
        genuine_spans = [
            span
            for span in spans_by_number[number]
            if not _is_absorbed_by_a_longer_label(number, span)
        ]
        if genuine_spans:
            referenced.append((number, from_id, genuine_spans[0]))
    return referenced


def _snippet(text: str, marker: str, radius: int = 8) -> str:
    index = text.find(marker)
    if index == -1:
        return marker
    start = max(0, index - radius)
    end = min(len(text), index + len(marker) + radius)
    return text[start:end]


def _snippet_from_span(text: str, span: tuple[int, int], radius: int = 8) -> str:
    start, end = span
    start = max(0, start - radius)
    end = min(len(text), end + radius)
    return text[start:end]
