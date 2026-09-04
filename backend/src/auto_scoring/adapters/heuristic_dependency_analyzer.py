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
            text = " ".join(
                part
                for part in (question.prompt_text, question.model_answer, question.rubric_text)
                if part
            )
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
            referenced = [
                (number, from_id)
                for number, from_id in by_number.items()
                if from_id != question.question_id and _contains_question_number(text, number)
            ]

            if referenced:
                for number, from_id in referenced:
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
                                f"{number}への参照表現「{_snippet_for_number(text, number)}」を検出"
                            ),
                            confidence=0.8 if matched_signal else 0.5,
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


def _contains_question_number(text: str, number: str) -> bool:
    return _question_number_pattern(number).search(text) is not None


def _snippet(text: str, marker: str, radius: int = 8) -> str:
    index = text.find(marker)
    if index == -1:
        return marker
    start = max(0, index - radius)
    end = min(len(text), index + len(marker) + radius)
    return text[start:end]


def _snippet_for_number(text: str, number: str, radius: int = 8) -> str:
    match = _question_number_pattern(number).search(text)
    if match is None:
        return number
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return text[start:end]
