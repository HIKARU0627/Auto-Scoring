"""HTTP boundary for the dependency-graph feature (Issue #26).

Thin per `AGENTS.md` "Architecture": every handler here only does request
parsing, opens one `SqlAlchemyUnitOfWork` per request, calls into the domain
(`auto_scoring.domain.dependency_graph`) and the analyzer port
(`auto_scoring.domain.dependency_analysis`), and translates the result to a
Pydantic response. This is the boundary the future テスト設定画面 (test
settings screen) will call to show/edit/confirm a test's dependency graph.

Endpoints (mounted under `/tests/{test_id}/dependency-graph`, all behind the
sidecar's bearer-token auth):

* ``POST /analyze`` -- generate candidates as a brand-new version, always.
  Never updates an existing (even still-DRAFT) version in place: a client
  reviewing an older draft must keep seeing exactly what it fetched, so a
  concurrent re-analysis cannot silently change what that client's `/confirm`
  would apply (see `confirm` below).
* ``GET  ``          -- the latest version, with its parallel-execution layers.
* ``GET  /versions``  -- every version, oldest first (Issue #26: 古いgraphの
  参照を保つ -- see docs/dependency-graph.md).
* ``POST /confirm``   -- human review step: replace the reviewed version's
  edges with the human-reviewed set and lock it. The request pins the exact
  version it reviewed; 404/409 if that version does not exist or is already
  confirmed.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
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
from auto_scoring.domain.models import JobSaveConflict, reissue_job_for_graph_version

#: Bound on retries when two concurrent /analyze calls race for the same
#: next version number (see `analyze` below). Each retry re-reads the latest
#: version, so this only needs to cover genuinely-overlapping writers, not
#: sustained contention.
_MAX_VERSION_ALLOCATION_ATTEMPTS = 5


def _now() -> datetime:
    """A naive UTC timestamp, matching how SQLite's DateTime column round-trips.

    See tests/support.py for the same convention on the test side.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _as_utc(value: datetime | None) -> datetime | None:
    """Mark a naive (DB-stored) UTC timestamp as UTC for the API boundary.

    A naive datetime serializes over HTTP with no offset/`Z`, and the
    generated Dart client's ISO-8601 parser then reads it as local time --
    a real skew (e.g. 9h in JST). Domain/DB values stay naive (see `_now`);
    only response payloads need the explicit `tzinfo`.
    """
    return value.replace(tzinfo=UTC) if value is not None else None


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
    # Typed as the domain enum (not `str`) so Pydantic itself rejects an
    # unknown provision at request-validation time (422) instead of the
    # handler raising an uncaught ValueError -> 500 when converting it.
    provides: list[DependencyProvision]
    rationale: str
    confidence: float | None = None

    def to_domain(self) -> DependencyEdge:
        return DependencyEdge(
            from_question_id=self.from_question_id,
            to_question_id=self.to_question_id,
            provides=tuple(self.provides),
            rationale=self.rationale,
            confidence=self.confidence,
        )

    @classmethod
    def from_domain(cls, edge: DependencyEdge) -> DependencyEdgeModel:
        return cls(
            from_question_id=edge.from_question_id,
            to_question_id=edge.to_question_id,
            provides=list(edge.provides),
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
    # The version the caller reviewed. Pinning it (rather than always
    # confirming "whatever is latest") stops a stale review from landing on
    # a different, unreviewed version that a concurrent /analyze created in
    # between (see `confirm` below).
    version: int
    # No default: an empty list must be a deliberate "no dependencies"
    # decision, not an accidental omission that would clear every draft
    # candidate and unresolved entry (see `confirm` below).
    edges: list[DependencyEdgeModel]


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
            created_at=graph.created_at.replace(tzinfo=UTC),
            confirmed_at=_as_utc(graph.confirmed_at),
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

    def _validate_overrides(
        overrides: Sequence[QuestionTextOverride], known_question_ids: set[str]
    ) -> None:
        """Reject overrides that silently would not do what the caller asked.

        A duplicate `question_id` would otherwise have all but the last entry
        dropped, and an unknown `question_id` would be ignored outright --
        both leave the analyzer reading different text than the caller sent,
        while the request still reports success.
        """
        seen: set[str] = set()
        duplicates: set[str] = set()
        for override in overrides:
            if override.question_id in seen:
                duplicates.add(override.question_id)
            seen.add(override.question_id)
        if duplicates:
            raise HTTPException(
                422, detail=f"duplicate question_id in overrides: {sorted(duplicates)}"
            )
        unknown = seen - known_question_ids
        if unknown:
            raise HTTPException(422, detail=f"unknown question_id in overrides: {sorted(unknown)}")

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
            # `or` would treat a deliberate `""` override (caller explicitly
            # excluding the saved rubric text from analysis) the same as "no
            # override was sent", falling back to `default_rubric_text` --
            # the analyzer would then read text the caller asked it not to
            # (Issue #26 review). Only an *absent* field (`None`) falls back.
            prompt_text = override.prompt_text if override is not None else None
            rubric_text = override.rubric_text if override is not None else None
            infos.append(
                QuestionInfo(
                    question_id=question.id,
                    number=question.number,
                    page=question.page,
                    prompt_text=prompt_text if prompt_text is not None else "",
                    model_answer=question.model_answer,
                    rubric_text=rubric_text if rubric_text is not None else default_rubric_text,
                )
            )
        return infos

    def _next_version(uow: SqlAlchemyUnitOfWork, test_id: str) -> int:
        """Always the next integer -- analyze() never reuses an existing version.

        Reusing the latest version while it was still DRAFT used to let a
        concurrent `/analyze` silently rewrite the exact draft another client
        was reviewing, so that client's later `/confirm` (pinned to that
        version) would apply its stale-reviewed edges to content it never
        saw. Every analysis is its own immutable version instead; an older
        draft nobody confirmed is simply superseded, never mutated.
        """
        latest = uow.dependency_graphs.get_latest(test_id)
        return latest.version + 1 if latest is not None else 1

    @router.post("/analyze", response_model=DependencyGraphResponse)
    def analyze(
        test_id: str,
        request: AnalyzeRequest,
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> DependencyGraphResponse:
        questions = uow.questions.list_for_test(test_id)
        if not questions:
            raise HTTPException(404, detail=f"test {test_id!r} has no questions to analyze")

        _validate_overrides(request.overrides, {q.id for q in questions})
        infos = _question_infos(uow, test_id, request.overrides)
        result = analyzer.analyze(infos)

        # Version allocation is read-then-write (`_next_version` reads the
        # latest, we insert one higher) and not protected by a lock, so two
        # overlapping /analyze calls can both compute the same next version.
        # SQLite serializes the actual writes, so only the second insert can
        # fail -- on the `(test_id, version)` unique constraint -- at which
        # point we roll back (the transaction is aborted) and pick a fresh
        # version rather than surface a raw IntegrityError as a 500.
        graph: DependencyGraph | None = None
        for _attempt in range(_MAX_VERSION_ALLOCATION_ATTEMPTS):
            version = _next_version(uow, test_id)
            try:
                candidate = DependencyGraph.from_candidates(
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
                uow.dependency_graphs.save(candidate)
            except IntegrityError:
                uow.rollback()
                continue
            except DependencyGraphError as error:
                raise HTTPException(409, detail=str(error)) from error

            graph = candidate
            break

        if graph is None:
            raise HTTPException(
                409,
                detail=(
                    f"could not allocate a new dependency graph version for test {test_id!r} "
                    "after several concurrent attempts; please retry"
                ),
            )

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
        # Pinned to the version the caller reviewed -- never "whatever is
        # latest" -- so a stale review can never land on a different,
        # unreviewed version (see the module docstring and ConfirmRequest).
        graph = uow.dependency_graphs.get(f"{test_id}:v{request.version}")
        if graph is None or graph.test_id != test_id:
            raise HTTPException(
                404,
                detail=f"test {test_id!r} has no dependency graph version {request.version}",
            )
        if graph.status is DependencyGraphStatus.CONFIRMED:
            raise HTTPException(
                409,
                detail=(
                    f"dependency graph for test {test_id!r} v{request.version} is already "
                    "confirmed; run /analyze to start a new version before confirming again"
                ),
            )

        # A *later* version may already be the active confirmed one (e.g. v2
        # was confirmed while this v1 review was still in flight). Confirming
        # v1 now would create two simultaneously-CONFIRMED versions, and the
        # job-invalidation step below would cancel v2's jobs and requeue them
        # against the now-stale v1 -- graph and job state would disagree
        # about which version is actually active. Reject it instead.
        active_confirmed = uow.dependency_graphs.get_latest_confirmed(test_id)
        if active_confirmed is not None and active_confirmed.version > request.version:
            raise HTTPException(
                409,
                detail=(
                    f"test {test_id!r} already has a newer confirmed version "
                    f"(v{active_confirmed.version}); v{request.version} is stale and can no "
                    "longer be confirmed"
                ),
            )

        # The test's question set may have changed since this version was
        # analyzed (a question added/removed between /analyze and /confirm).
        # Confirming a snapshot that no longer matches the test would pass
        # `can_start_submission_processing` while missing/including the wrong
        # questions -- require a fresh /analyze instead.
        current_question_ids = {q.id for q in uow.questions.list_for_test(test_id)}
        if current_question_ids != graph.question_ids:
            raise HTTPException(
                409,
                detail=(
                    f"test {test_id!r}'s questions changed since v{request.version} was "
                    "analyzed; run /analyze again before confirming"
                ),
            )

        try:
            confirmed = graph.confirm(
                edges=[edge.to_domain() for edge in request.edges], confirmed_at=_now()
            )
        except DependencyGraphError as error:
            raise HTTPException(422, detail=str(error)) from error

        # The checks above (status / active-confirmed / question set) read
        # before this write and are not by themselves atomic: two concurrent
        # `/confirm` calls can both pass them before either writes. The
        # actual write is a compare-and-set (`try_confirm`), so only one of
        # two racing confirms can ever win; the loser gets a 409 here instead
        # of silently overwriting the winner's edges or reissuing jobs
        # against a version that lost the race (Issue #26 review).
        if not uow.dependency_graphs.try_confirm(confirmed):
            raise HTTPException(
                409,
                detail=(
                    f"dependency graph for test {test_id!r} v{request.version} could not be "
                    "confirmed -- it was confirmed by another request, or a newer version was, "
                    "in the meantime; re-fetch and retry"
                ),
            )

        # Issue #26 acceptance: confirming a new version must invalidate and
        # recreate any still-incomplete job left over from a superseded one,
        # in the same transaction as the confirmation itself.
        for stale_job in uow.jobs.list_incomplete_for_stale_versions(test_id, confirmed.version):
            cancelled, replacement = reissue_job_for_graph_version(
                stale_job, new_version=confirmed.version, new_id=str(uuid4()), at=_now()
            )
            try:
                uow.jobs.save(cancelled)
            except JobSaveConflict:
                # Another writer (a worker finishing this job) changed its
                # state after we listed it as stale. Do not create a
                # replacement for it -- the job we meant to cancel no longer
                # exists in the state we read, so a duplicate QUEUED
                # replacement would risk double-processing the same work.
                continue
            uow.jobs.add(replacement)

        uow.commit()
        return DependencyGraphResponse.from_domain(confirmed)

    return router
