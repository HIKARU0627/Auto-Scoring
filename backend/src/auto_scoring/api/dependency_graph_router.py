"""HTTP boundary for the dependency-graph feature (Issue #26).

Thin per `AGENTS.md` "Architecture": every handler here only does request
parsing, opens one `SqlAlchemyUnitOfWork` per request, calls into the domain
(`auto_scoring.domain.dependency_graph`) and the analyzer port
(`auto_scoring.domain.dependency_analysis`), and translates the result to a
Pydantic response. This is the boundary the future テスト設定画面 (test
settings screen) will call to show/edit/confirm a test's dependency graph.

Endpoints (mounted under `/tests/{test_id}/dependency-graph`, all behind the
sidecar's bearer-token auth):

* ``POST /analyze`` -- (re)generate candidates for the current version. If the
  latest saved version is still DRAFT it is replaced in place; if it is
  CONFIRMED (or there is none yet) a new version is started.
* ``GET  ``          -- the latest version, with its parallel-execution layers.
* ``GET  /versions``  -- every version, oldest first (Issue #26: 古いgraphの
  参照を保つ -- see docs/dependency-graph.md).
* ``POST /confirm``   -- human review step: replace the latest DRAFT's edges
  with the reviewed set and lock it. 409 if there is no draft to confirm.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.heuristic_dependency_analyzer import ReferenceHeuristicDependencyAnalyzer
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.dependency_analysis import DependencyAnalyzer, QuestionInfo
from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyGraphError,
    DependencyGraphStatus,
    DependencyProvision,
    UnresolvedQuestion,
)


def _now() -> datetime:
    """A naive UTC timestamp, matching how SQLite's DateTime column round-trips.

    See tests/support.py for the same convention on the test side.
    """
    return datetime.now(UTC).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #
class QuestionTextOverride(BaseModel):
    """Extracted PDF text for one question, supplied by the caller.

    The MVP question record (Issue #11) does not yet store 問題文 text
    extracted from the model-answer/manual PDFs, so the analyze request
    carries it explicitly -- once PDF text extraction exists this becomes the
    default and overrides stay optional.
    """

    question_id: str
    prompt_text: str | None = None
    rubric_text: str | None = None


class AnalyzeRequest(BaseModel):
    overrides: list[QuestionTextOverride] = Field(default_factory=list)


class DependencyEdgeModel(BaseModel):
    from_question_id: str
    to_question_id: str
    provides: list[str]
    rationale: str
    confidence: float | None = None

    def to_domain(self) -> DependencyEdge:
        return DependencyEdge(
            from_question_id=self.from_question_id,
            to_question_id=self.to_question_id,
            provides=tuple(DependencyProvision(p) for p in self.provides),
            rationale=self.rationale,
            confidence=self.confidence,
        )

    @classmethod
    def from_domain(cls, edge: DependencyEdge) -> DependencyEdgeModel:
        return cls(
            from_question_id=edge.from_question_id,
            to_question_id=edge.to_question_id,
            provides=[p.value for p in edge.provides],
            rationale=edge.rationale,
            confidence=edge.confidence,
        )


class UnresolvedQuestionModel(BaseModel):
    question_id: str
    reason: str

    @classmethod
    def from_domain(cls, unresolved: UnresolvedQuestion) -> UnresolvedQuestionModel:
        return cls(question_id=unresolved.question_id, reason=unresolved.reason)


class ConfirmRequest(BaseModel):
    edges: list[DependencyEdgeModel] = Field(default_factory=list)


class DependencyGraphResponse(BaseModel):
    id: str
    test_id: str
    version: int
    status: str
    question_ids: list[str]
    edges: list[DependencyEdgeModel]
    unresolved: list[UnresolvedQuestionModel]
    layers: list[list[str]]
    created_at: datetime
    confirmed_at: datetime | None = None

    @classmethod
    def from_domain(cls, graph: DependencyGraph) -> DependencyGraphResponse:
        return cls(
            id=graph.id,
            test_id=graph.test_id,
            version=graph.version,
            status=graph.status.value,
            question_ids=sorted(graph.question_ids),
            edges=[DependencyEdgeModel.from_domain(edge) for edge in graph.edges],
            unresolved=[UnresolvedQuestionModel.from_domain(u) for u in graph.unresolved],
            layers=[list(layer) for layer in graph.topological_layers()],
            created_at=graph.created_at,
            confirmed_at=graph.confirmed_at,
        )


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #
def build_dependency_graph_router(
    session_factory: sessionmaker[Session],
    *,
    analyzer: DependencyAnalyzer | None = None,
) -> APIRouter:
    """Build the router. One `SqlAlchemyUnitOfWork` is opened per request."""
    analyzer = analyzer or ReferenceHeuristicDependencyAnalyzer()
    router = APIRouter(prefix="/tests/{test_id}/dependency-graph", tags=["dependency-graph"])

    def _uow() -> Iterator[SqlAlchemyUnitOfWork]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            yield uow

    uow_dependency = Depends(_uow)

    def _question_infos(
        uow: SqlAlchemyUnitOfWork, test_id: str, overrides: Sequence[QuestionTextOverride]
    ) -> list[QuestionInfo]:
        overrides_by_id = {override.question_id: override for override in overrides}
        infos: list[QuestionInfo] = []
        for question in uow.questions.list_for_test(test_id):
            override = overrides_by_id.get(question.id)
            rubric = uow.rubrics.get_for_question(question.id)
            default_rubric_text = (
                "、".join(c.description for c in rubric.criteria) if rubric is not None else None
            )
            infos.append(
                QuestionInfo(
                    question_id=question.id,
                    number=question.number,
                    page=question.page,
                    prompt_text=(override.prompt_text if override else None) or "",
                    model_answer=question.model_answer,
                    rubric_text=(override.rubric_text if override else None) or default_rubric_text,
                )
            )
        return infos

    def _next_version(uow: SqlAlchemyUnitOfWork, test_id: str) -> int:
        latest = uow.dependency_graphs.get_latest(test_id)
        if latest is None:
            return 1
        if latest.status is DependencyGraphStatus.DRAFT:
            return latest.version
        return latest.version + 1

    @router.post("/analyze", response_model=DependencyGraphResponse)
    def analyze(
        test_id: str,
        request: AnalyzeRequest,
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> DependencyGraphResponse:
        questions = uow.questions.list_for_test(test_id)
        if not questions:
            raise HTTPException(404, detail=f"test {test_id!r} has no questions to analyze")

        infos = _question_infos(uow, test_id, request.overrides)
        result = analyzer.analyze(infos)
        version = _next_version(uow, test_id)

        try:
            graph = DependencyGraph.from_candidates(
                id=f"{test_id}:v{version}",
                test_id=test_id,
                version=version,
                question_ids=[q.id for q in questions],
                edges=result.edges,
                unresolved=result.unresolved,
                created_at=_now(),
            )
        except DependencyGraphError as error:
            raise HTTPException(422, detail=str(error)) from error

        try:
            uow.dependency_graphs.save(graph)
        except DependencyGraphError as error:
            raise HTTPException(409, detail=str(error)) from error
        uow.commit()
        return DependencyGraphResponse.from_domain(graph)

    @router.get("", response_model=DependencyGraphResponse)
    def get_latest(
        test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> DependencyGraphResponse:
        graph = uow.dependency_graphs.get_latest(test_id)
        if graph is None:
            raise HTTPException(404, detail=f"test {test_id!r} has no dependency graph yet")
        return DependencyGraphResponse.from_domain(graph)

    @router.get("/versions", response_model=list[DependencyGraphResponse])
    def list_versions(
        test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> list[DependencyGraphResponse]:
        return [
            DependencyGraphResponse.from_domain(g)
            for g in uow.dependency_graphs.list_versions(test_id)
        ]

    @router.post("/confirm", response_model=DependencyGraphResponse)
    def confirm(
        test_id: str,
        request: ConfirmRequest,
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> DependencyGraphResponse:
        latest = uow.dependency_graphs.get_latest(test_id)
        if latest is None:
            raise HTTPException(404, detail=f"test {test_id!r} has no dependency graph yet")
        if latest.status is DependencyGraphStatus.CONFIRMED:
            raise HTTPException(
                409,
                detail=(
                    f"dependency graph for test {test_id!r} is already confirmed "
                    f"at v{latest.version}; run /analyze to start a new version before "
                    "confirming again"
                ),
            )

        try:
            confirmed = latest.confirm(
                edges=[edge.to_domain() for edge in request.edges], confirmed_at=_now()
            )
        except DependencyGraphError as error:
            raise HTTPException(422, detail=str(error)) from error

        uow.dependency_graphs.save(confirmed)
        uow.commit()
        return DependencyGraphResponse.from_domain(confirmed)

    return router
