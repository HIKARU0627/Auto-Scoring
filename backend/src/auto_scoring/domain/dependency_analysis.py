"""Port for generating dependency-graph candidates (Issue #26).

Concrete analyzers live in `auto_scoring.adapters` (see `AGENTS.md`
"Architecture" -- `adapters/` holds `PdfEngine`, `OCRProvider`, `AIProvider`,
repository implementations, and now `DependencyAnalyzer` implementations).
This module only describes the contract, so the domain and the confirm/persist
flow never depend on how candidates get produced -- a future `AIProvider`-backed
analyzer can replace today's heuristic one without touching callers. See
docs/dependency-graph.md for the current adapter choice and its rationale.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from auto_scoring.domain.dependency_graph import DependencyEdge, UnresolvedQuestion


@dataclass(frozen=True, kw_only=True)
class QuestionInfo:
    """Per-question inputs Issue #26 lists as candidate-generation sources:
    問題文、模範解答、採点マニュアル、ページ/設問構造。
    """

    question_id: str
    number: str
    page: int
    prompt_text: str = ""
    model_answer: str | None = None
    rubric_text: str | None = None


@dataclass(frozen=True, kw_only=True)
class DependencyAnalysisResult:
    edges: tuple[DependencyEdge, ...]
    unresolved: tuple[UnresolvedQuestion, ...]


class DependencyAnalyzer(Protocol):
    """Produces dependency candidates for one test's questions.

    A question must never be silently treated as "no dependency" when the
    analyzer found ambiguous signal -- put it in `unresolved` instead (Issue
    #26: "分析不能・曖昧な関係は…要確認として…表示する").
    """

    def analyze(self, questions: Sequence[QuestionInfo]) -> DependencyAnalysisResult: ...
