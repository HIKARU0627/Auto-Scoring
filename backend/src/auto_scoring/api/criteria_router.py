"""HTTP boundary for reading 配点 and 採点基準 out of a test's 採点基準PDF,
and for the human review that follows (Issue #103).

* ``POST /tests/{test_id}/criteria/extract`` -- render every page of the
  registered 採点基準PDF and have the configured multimodal model read it.
  Overwrites whatever DRAFT was there (same contract as
  ``/profile/analyze``); rejected once the criteria are confirmed.
* ``GET /tests/{test_id}/criteria`` -- the current draft or confirmed set.
* ``PUT /tests/{test_id}/criteria`` -- replace the questions with a
  human-reviewed set. Still DRAFT; this is not the confirm step. **Creates
  the draft when none exists**, which is the escape hatch Issue #95
  decision 8 requires: a reviewer whose extraction found nothing -- or who
  never ran one -- types every question in by hand and still gets to a
  gradable test.
* ``POST /tests/{test_id}/criteria/confirm`` -- the human sign-off. Refuses
  while any question's 配点 is 不明, then writes the test's
  `Question`/`Rubric` rows.

**Confirming here is one of two paths to the same rows.** The other is
``/profile/confirm``. Both call
`domain.test_registration.build_questions_and_rubrics` with both artefacts,
so whichever runs last produces the same result and the reviewer can work in
either order -- see that function's docstring for which field comes from
which artefact, and `api.test_artifact_lock` for why they share a lock.

Nothing in this module logs or returns any part of the extraction request or
the raw model response. The pages are a school's copyrighted material
(Issue #95 decision 7: sending them to the configured provider is allowed,
publishing them is not); what crosses back out of here is the validated,
reviewable result and nothing else.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.criteria_extraction.source import (
    MAX_CRITERIA_PAGES,
    build_extraction_request,
    criteria_pdf_path,
)
from auto_scoring.adapters.local.criteria_store import CriteriaStore
from auto_scoring.adapters.local.profile_store import ProfileStore
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.test_artifact_lock import TestArtifactLocks
from auto_scoring.domain.ai_provider import ProviderUnavailable, SchemaViolation
from auto_scoring.domain.criteria_extraction import (
    CriteriaDraft,
    CriteriaError,
    CriteriaExtractor,
    CriteriaItem,
    CriteriaQuestion,
    CriteriaStatus,
    CriteriaTotals,
    CriterionKind,
    criteria_totals,
    draft_from_extraction,
    ensure_confirmable,
)
from auto_scoring.domain.models import DomainError, Test
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.profile import Profile, ProfileStatus, Region
from auto_scoring.domain.test_registration import (
    QuestionsInUseError,
    build_questions_and_rubrics,
    ensure_questions_can_be_rebuilt,
)

#: Every integer that crosses this module's wire boundary.
#:
#: Pydantic's default (lax) mode coerces on the way in: a body carrying
#: ``"points": true`` becomes **1** and ``"points": "5"`` becomes 5, and both
#: reach `to_domain()`, the file store and the confirm step as if a person
#: had typed them. This feature already refuses a malformed *model* response
#: (`domain.criteria_extraction` is ``strict=True``) and a malformed *file*
#: (`CriteriaDraft.from_dict` rejects a bool where points belong) -- the
#: human-editing path was the one door left open, and it is the wrong door
#: to leave open: a wrong number here is a wrong maximum for every
#: submission of that test (code review P2-1; AGENTS.md "Security":
#: validate every input that crosses a trust boundary).
#:
#: Applied per field rather than as ``ConfigDict(strict=True)`` on the model.
#: Model-level strict also governs the enum fields, and FastAPI validates a
#: request from an already-parsed Python dict -- where a strict enum rejects
#: the JSON string ``"add"`` because it is not a `CriterionKind` instance.
#: (``model_validate_json`` does not have this problem, which is why the
#: domain schema can be strict wholesale.) Narrowing to the integers keeps
#: the enums working over the wire and still closes the coercion the review
#: found.
StrictInt = Annotated[int, Field(strict=True)]


class CriteriaItemModel(BaseModel):
    """One marking criterion, over the wire."""

    description: str
    #: Required, not defaulted: whether a criterion adds or deducts is never
    #: unknown in the way its point value can be, and a default would make
    #: the generated client's field nullable -- turning "the caller did not
    #: say" into "assume 加点", which inverts a deduction.
    kind: CriterionKind
    points: StrictInt | None = None

    @classmethod
    def from_domain(cls, item: CriteriaItem) -> CriteriaItemModel:
        return cls(description=item.description, kind=item.kind, points=item.points)

    def to_domain(self) -> CriteriaItem:
        return CriteriaItem(description=self.description, kind=self.kind, points=self.points)


class CriteriaQuestionModel(BaseModel):
    """One question's allocation and criteria, over the wire.

    ``points`` being ``null`` is the 不明 the whole feature is built around:
    it means "this could not be read", never 0. The app renders it as 不明
    and refuses to confirm while any remain.
    """

    number: str
    points: StrictInt | None = None
    model_answer: str | None = None
    #: Required (possibly empty). "No criteria" is an empty list, never an
    #: absent field -- keeping it required is what makes the generated
    #: client's list non-nullable, so no caller has to decide what a missing
    #: list means.
    criteria: list[CriteriaItemModel]
    source_pages: list[StrictInt]
    note: str | None = None

    @classmethod
    def from_domain(cls, question: CriteriaQuestion) -> CriteriaQuestionModel:
        return cls(
            number=question.number,
            points=question.points,
            model_answer=question.model_answer,
            criteria=[CriteriaItemModel.from_domain(item) for item in question.criteria],
            source_pages=list(question.source_pages),
            note=question.note,
        )

    def to_domain(self) -> CriteriaQuestion:
        return CriteriaQuestion(
            number=self.number,
            points=self.points,
            model_answer=self.model_answer,
            criteria=tuple(item.to_domain() for item in self.criteria),
            source_pages=tuple(self.source_pages),
            note=self.note,
        )


class CriteriaTotalsModel(BaseModel):
    """The sum, the unknown count, and the comparison with the document's
    own stated total.

    A snapshot of what is **saved**. The screen recomputes all of it from
    whatever the reviewer has typed but not yet saved -- showing this value
    beside unsaved edits would report a total for a list that is no longer on
    screen, the same trap ``test_settings_page.dart`` already avoids for the
    dependency graph's execution layers.
    """

    known_points: StrictInt
    unknown_count: StrictInt
    declared_total_points: StrictInt | None = None
    declared_difference: StrictInt | None = None
    is_complete: bool

    @classmethod
    def from_domain(cls, totals: CriteriaTotals) -> CriteriaTotalsModel:
        return cls(
            known_points=totals.known_points,
            unknown_count=totals.unknown_count,
            declared_total_points=totals.declared_total_points,
            declared_difference=totals.declared_difference,
            is_complete=totals.is_complete,
        )


class CriteriaResponse(BaseModel):
    """A test's 配点と採点基準, as the review screen sees it."""

    test_id: str
    status: CriteriaStatus
    #: Compare-and-set token for ``/criteria/confirm`` -- must match the
    #: revision the reviewer actually looked at. Same contract, and the same
    #: reason, as ``domain.profile.Profile.revision``.
    revision: StrictInt
    #: Whether anything was ever read from the PDF. Distinguishes "the
    #: extraction ran and found nothing" from "nobody has run it", which
    #: otherwise look identical (both are an empty list).
    extracted: bool
    questions: list[CriteriaQuestionModel]
    declared_total_points: StrictInt | None = None
    #: 1-based pages the model reported it could not read. Kept after review
    #: rather than cleared by an edit: it is a record of what the extraction
    #: could not see, and it stops being true only when a new extraction
    #: replaces it.
    unreadable_pages: list[StrictInt]
    note: str | None = None
    totals: CriteriaTotalsModel

    @classmethod
    def from_domain(cls, draft: CriteriaDraft) -> CriteriaResponse:
        return cls(
            test_id=draft.test_id,
            status=draft.status,
            revision=draft.revision,
            extracted=draft.extracted,
            questions=[CriteriaQuestionModel.from_domain(question) for question in draft.questions],
            declared_total_points=draft.declared_total_points,
            unreadable_pages=list(draft.unreadable_pages),
            note=draft.note,
            totals=CriteriaTotalsModel.from_domain(criteria_totals(draft)),
        )


class CriteriaEstimateResponse(BaseModel):
    """What one extraction would send, and what it would cost -- answered
    *before* anything is sent (code review P2-2).

    Pressing 抽出 uploads every page of the criteria PDF to a paid provider,
    and pressing it again does it again. A reviewer is entitled to see the
    size of that before it happens, the same way Issue #101's intake screen
    shows its own call count and estimate.
    """

    #: How many page images the extraction would send.
    page_count: StrictInt
    #: The most this app will read in one call
    #: (`adapters.criteria_extraction.source.MAX_CRITERIA_PAGES`), so the
    #: screen can say "over the limit" before the reviewer waits for a 422.
    max_pages: StrictInt
    #: Price per page, if this install has been told one. **``null`` is not
    #: zero** -- zero is a reviewer stating their usage is free, null is this
    #: app admitting it does not know and saying so on screen instead of
    #: showing an invented figure (the wording Issue #101 settled on for the
    #: intake screen).
    #:
    #: Always ``null`` today: nothing in this app knows a per-page price.
    #: Issue #101 stores a per-*file* classification price, which is a
    #: different unit and must not be reused here as if it were the same
    #: number. Wiring a real per-page price is a one-line change in
    #: `estimate_criteria` once one exists.
    unit_cost: float | None = None
    #: ``page_count * unit_cost``, or ``null`` when :attr:`unit_cost` is.
    estimated_cost: float | None = None


class UpdateCriteriaRequest(BaseModel):
    """The reviewed question set to save.

    ``declared_total_points`` is editable because the reviewer may be
    correcting a total the model misread, or clearing one it invented from a
    footer page number.
    """

    questions: list[CriteriaQuestionModel]
    declared_total_points: StrictInt | None = None


class ConfirmCriteriaRequest(BaseModel):
    """The revision the reviewer is signing off on."""

    revision: StrictInt


def build_criteria_router(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    pdf_engine: PdfEngine,
    extractor: CriteriaExtractor,
    *,
    locks: TestArtifactLocks | None = None,
    pdfium_lock: threading.Lock | None = None,
) -> APIRouter:
    """Build the router. One `SqlAlchemyUnitOfWork` is opened per request.

    ``locks`` must be the *same* :class:`TestArtifactLocks` passed to
    `api.test_registration_router.build_test_registration_router` -- see
    that module for the interleave a second, private registry would allow.
    A private one is created when omitted (schema export, unit tests that
    never confirm a profile and a criteria draft concurrently).

    ``pdfium_lock`` must be the *same* lock `api.app.create_app` shares with
    answer intake, PDF export and profile analysis. **pypdfium2 is not safe
    to call from several threads of one process**, and this router renders
    every page of a criteria PDF -- so without it, an extraction overlapping
    an intake or an export reaches PDFium concurrently and can corrupt a
    render or take the process down (code review P1). Every other PDF-
    touching path in this app already takes it; this one was the only
    hold-out.
    """
    criteria_store = CriteriaStore(store.root)
    profile_store = ProfileStore(store.root)
    test_locks = locks or TestArtifactLocks()
    render_lock = pdfium_lock or threading.Lock()
    router = APIRouter(tags=["criteria"])

    def _uow() -> Iterator[SqlAlchemyUnitOfWork]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            yield uow

    uow_dependency = Depends(_uow)

    def _get_test_or_404(uow: SqlAlchemyUnitOfWork, test_id: str) -> Test:
        test = uow.tests.get(test_id)
        if test is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"test {test_id!r} not found")
        return test

    def _load_draft(test_id: str) -> CriteriaDraft | None:
        try:
            return criteria_store.load(test_id)
        except FileNotFoundError:
            return None

    def _load_draft_or_404(test_id: str) -> CriteriaDraft:
        draft = _load_draft(test_id)
        if draft is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=(
                    f"test {test_id!r} has no 採点基準 yet; run /criteria/extract or "
                    "save a hand-entered set with PUT /criteria first"
                ),
            )
        return draft

    def _confirmed_profile(test_id: str) -> Profile | None:
        """The test's profile, but only once a human has confirmed it.

        An unconfirmed profile's regions are still candidates nobody has
        checked; folding them into `Question` rows here would attach
        unreviewed coordinates to a reviewed set of points.
        """
        try:
            profile = profile_store.load(test_id)
        except FileNotFoundError:
            return None
        return profile if profile.status is ProfileStatus.CONFIRMED else None

    def _rebuild_questions(
        uow: SqlAlchemyUnitOfWork,
        test: Test,
        *,
        regions: tuple[Region, ...],
        criteria: CriteriaDraft,
    ) -> None:
        """Replace this test's `Question`/`Rubric` rows from both artefacts.

        Delete-and-rebuild rather than insert-if-missing, for the reason
        `confirm_profile` states: a retry after a partial failure must end
        up with exactly this set, not this set plus whatever an earlier
        attempt left behind.
        """
        # Before the delete below, not after: six tables cascade off
        # `questions.id`, so rebuilding a test that already has answers
        # destroys every answer image and every grade it has, and
        # re-inserting the same ids brings none of it back
        # (`ensure_questions_can_be_rebuilt`).
        try:
            ensure_questions_can_be_rebuilt(
                test_id=test.id,
                submission_count=len(uow.submissions.list_for_test(test.id)),
            )
        except QuestionsInUseError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        try:
            questions, rubrics = build_questions_and_rubrics(
                test.id,
                regions,
                default_scoring_method=test.default_scoring_method,
                criteria=criteria,
            )
        except DomainError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        uow.questions.delete_for_test(test.id)
        for question in questions:
            uow.questions.add(question)
        for rubric in rubrics:
            uow.rubrics.add(rubric)
        uow.commit()

    @router.get("/tests/{test_id}/criteria/estimate", response_model=CriteriaEstimateResponse)
    def estimate_criteria(
        test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> CriteriaEstimateResponse:
        """How many pages an extraction would send, and what that would cost.

        Reads only the page count -- no rendering, no provider call, no
        charge. Takes the shared PDFium lock anyway: ``page_count`` opens the
        document, and this app serializes every PDF read for the reason
        `build_criteria_router` documents.
        """
        _get_test_or_404(uow, test_id)
        source = criteria_pdf_path(store, test_id)
        try:
            with render_lock:
                page_count = pdf_engine.page_count(source)
        except FileNotFoundError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"test {test_id!r} の採点基準PDFが見つかりません。"
                    "登録し直してから抽出してください。"
                ),
            ) from exc
        except Exception as exc:
            # A corrupt or unreadable PDF must not become a 500 on a screen
            # whose whole job is to answer "is it safe to press 抽出?".
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"採点基準PDFのページ数を読み取れませんでした: {type(exc).__name__}",
            ) from None
        return CriteriaEstimateResponse(page_count=page_count, max_pages=MAX_CRITERIA_PAGES)

    @router.post("/tests/{test_id}/criteria/extract", response_model=CriteriaResponse)
    def extract_criteria(
        test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> CriteriaResponse:
        """Read the registered 採点基準PDF with the configured model.

        Every page is rendered and sent as an image. That is not a fallback
        for a failed text extraction -- 6 of the 11 measured subjects have no
        text layer at all, and they are the subjects whose answers are
        formulae, so the image path is the only one that covers them
        (``adapters.criteria_extraction.source``).

        The result is a **proposal**. It is stored as a DRAFT and nothing
        downstream reads it until a human confirms it.

        Deliberately a **synchronous** handler, like ``/profile/analyze``:
        FastAPI runs those in its worker threadpool, so the per-test lock
        below and the minute-long provider call are held off the event loop.
        Written as ``async def`` with ``await to_thread(...)`` inside, the
        two blocking calls would move off the loop but ``with
        test_locks.for_test(...)`` would not -- a second extraction of the
        same test would then block the whole sidecar for as long as the
        first one takes to answer (code review of this Issue).
        """
        _get_test_or_404(uow, test_id)
        with test_locks.for_test(test_id):
            existing = _load_draft(test_id)
            if existing is not None and existing.status is CriteriaStatus.CONFIRMED:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=(
                        f"test {test_id!r}'s 採点基準 is already confirmed and cannot be "
                        "re-extracted"
                    ),
                )
            source = criteria_pdf_path(store, test_id)
            try:
                # `render_lock` covers the PDFium work and **stops there**.
                # Holding it across the provider call would serialize every
                # other PDF operation in the app behind a 7-53 second
                # network wait (measured over the real material) -- an
                # extraction started mid-afternoon would freeze answer
                # intake for the rest of it (code review P1).
                with render_lock:
                    request = build_extraction_request(pdf_engine, source)
            except FileNotFoundError as exc:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=(
                        f"test {test_id!r} の採点基準PDFが見つかりません。"
                        "登録し直してから抽出してください。"
                    ),
                ) from exc
            except CriteriaError as exc:
                raise HTTPException(422, detail=str(exc)) from exc

            try:
                output = extractor.extract(request)
            except SchemaViolation as exc:
                # The model answered, but not in a shape that can be
                # trusted with point values. 502, and **nothing is saved**:
                # a partially-parsed result would be indistinguishable on
                # screen from a real reading (Issue #103 acceptance
                # criterion 6). The message carries the adapter's own fixed
                # text only -- never the response body.
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        f"AI の応答が採点基準の形式に合いませんでした: {exc}。"
                        "配点は保存していません。もう一度実行するか、手で入力してください。"
                    ),
                ) from None
            except ProviderUnavailable as exc:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        f"AI provider に接続できませんでした: {exc}。"
                        "設定を確認するか、手で入力してください。"
                    ),
                ) from None

            # Bumped, not reset: a re-extraction changes a set the reviewer
            # may already have fetched, and must invalidate a confirm
            # pinned to the previous revision -- the same rule
            # `analyze_profile` applies to the profile.
            try:
                draft = draft_from_extraction(
                    test_id, output, revision=(existing.revision + 1 if existing else 1)
                )
            except CriteriaError as exc:
                # A schema-valid response that still cannot become a draft.
                # `draft_from_extraction` resolves the one such case found in
                # real material (repeated question numbers), so reaching here
                # means something new -- and Issue #103's first acceptance
                # criterion is that extraction does not fall over. Reported
                # as a bad gateway with nothing saved, exactly like a schema
                # violation, rather than escaping as a 500 that tells the
                # reviewer nothing and leaves no way forward.
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        f"AI の応答から採点基準を組み立てられませんでした: {exc}。"
                        "配点は保存していません。もう一度実行するか、手で入力してください。"
                    ),
                ) from None
            criteria_store.save(draft)
        return CriteriaResponse.from_domain(draft)

    @router.get("/tests/{test_id}/criteria", response_model=CriteriaResponse)
    def get_criteria(test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency) -> CriteriaResponse:
        _get_test_or_404(uow, test_id)
        return CriteriaResponse.from_domain(_load_draft_or_404(test_id))

    @router.put("/tests/{test_id}/criteria", response_model=CriteriaResponse)
    def update_criteria(
        test_id: str, request: UpdateCriteriaRequest, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> CriteriaResponse:
        """Save a reviewed (or entirely hand-entered) question set.

        Creates the draft when there is none. That upsert is the escape
        hatch Issue #95 decision 8 asks for: a subject whose criteria PDF
        the model could not read at all must still be enterable, and
        requiring an extraction to succeed first would make the failure
        unrecoverable on exactly the documents that need the fallback.

        Saving does not confirm. ``unreadable_pages`` and the extraction's
        own ``note`` are carried through untouched -- they describe what the
        extraction saw, and an edit does not change that.
        """
        _get_test_or_404(uow, test_id)
        with test_locks.for_test(test_id):
            existing = _load_draft(test_id)
            if existing is not None and existing.status is CriteriaStatus.CONFIRMED:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=f"test {test_id!r}'s 採点基準 is already confirmed and cannot be edited",
                )
            try:
                updated = CriteriaDraft(
                    test_id=test_id,
                    questions=tuple(question.to_domain() for question in request.questions),
                    declared_total_points=request.declared_total_points,
                    unreadable_pages=existing.unreadable_pages if existing else (),
                    note=existing.note if existing else None,
                    extracted=existing.extracted if existing else False,
                    # Bumped from whatever was saved, never reset -- see
                    # `CriteriaDraft.revision`.
                    revision=(existing.revision + 1) if existing else 1,
                )
            except CriteriaError as exc:
                raise HTTPException(422, detail=str(exc)) from exc
            criteria_store.save(updated)
        return CriteriaResponse.from_domain(updated)

    @router.post("/tests/{test_id}/criteria/confirm", response_model=CriteriaResponse)
    def confirm_criteria(
        test_id: str, request: ConfirmCriteriaRequest, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> CriteriaResponse:
        """Sign off on every point value, and write the test's questions.

        Refuses while any 配点 is 不明. That is the gate: `Question.points`
        is the maximum every grade for that question is computed against, so
        a value nobody read must be typed in by a person before it can reach
        the database -- never defaulted, never skipped
        (`ensure_confirmable`).
        """
        test = _get_test_or_404(uow, test_id)
        with test_locks.for_test(test_id):
            draft = _load_draft_or_404(test_id)
            if draft.status is CriteriaStatus.CONFIRMED:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=f"test {test_id!r}'s 採点基準 is already confirmed",
                )
            if draft.revision != request.revision:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=(
                        f"test {test_id!r}'s 採点基準 has changed since revision "
                        f"{request.revision} was reviewed (current revision: {draft.revision}); "
                        "reload and re-review before confirming"
                    ),
                )
            try:
                ensure_confirmable(draft)
                confirmed = draft.confirm()
            except CriteriaError as exc:
                raise HTTPException(422, detail=str(exc)) from exc

            profile = _confirmed_profile(test_id)
            _rebuild_questions(
                uow,
                test,
                regions=tuple(profile.regions) if profile is not None else (),
                criteria=confirmed,
            )

            # Saved after the rows are committed, for the same reason
            # `confirm_profile` saves its file last: if this write fails
            # (disk full), the rows are already durable and the handler can
            # simply be retried -- the rebuild above is idempotent.
            criteria_store.save(confirmed)
        return CriteriaResponse.from_domain(confirmed)

    return router
