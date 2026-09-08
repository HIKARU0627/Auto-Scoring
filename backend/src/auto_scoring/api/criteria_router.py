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

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.criteria_extraction.source import (
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
from auto_scoring.domain.test_registration import build_questions_and_rubrics


class CriteriaItemModel(BaseModel):
    """One marking criterion, over the wire."""

    description: str
    #: Required, not defaulted: whether a criterion adds or deducts is never
    #: unknown in the way its point value can be, and a default would make
    #: the generated client's field nullable -- turning "the caller did not
    #: say" into "assume 加点", which inverts a deduction.
    kind: CriterionKind
    points: int | None = None

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
    points: int | None = None
    model_answer: str | None = None
    #: Required (possibly empty). "No criteria" is an empty list, never an
    #: absent field -- keeping it required is what makes the generated
    #: client's list non-nullable, so no caller has to decide what a missing
    #: list means.
    criteria: list[CriteriaItemModel]
    source_pages: list[int]
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

    known_points: int
    unknown_count: int
    declared_total_points: int | None = None
    declared_difference: int | None = None
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
    revision: int
    #: Whether anything was ever read from the PDF. Distinguishes "the
    #: extraction ran and found nothing" from "nobody has run it", which
    #: otherwise look identical (both are an empty list).
    extracted: bool
    questions: list[CriteriaQuestionModel]
    declared_total_points: int | None = None
    #: 1-based pages the model reported it could not read. Kept after review
    #: rather than cleared by an edit: it is a record of what the extraction
    #: could not see, and it stops being true only when a new extraction
    #: replaces it.
    unreadable_pages: list[int]
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


class UpdateCriteriaRequest(BaseModel):
    """The reviewed question set to save.

    ``declared_total_points`` is editable because the reviewer may be
    correcting a total the model misread, or clearing one it invented from a
    footer page number.
    """

    questions: list[CriteriaQuestionModel]
    declared_total_points: int | None = None


class ConfirmCriteriaRequest(BaseModel):
    """The revision the reviewer is signing off on."""

    revision: int


def build_criteria_router(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    pdf_engine: PdfEngine,
    extractor: CriteriaExtractor,
    *,
    locks: TestArtifactLocks | None = None,
) -> APIRouter:
    """Build the router. One `SqlAlchemyUnitOfWork` is opened per request.

    ``locks`` must be the *same* :class:`TestArtifactLocks` passed to
    `api.test_registration_router.build_test_registration_router` -- see
    that module for the interleave a second, private registry would allow.
    A private one is created when omitted (schema export, unit tests that
    never confirm a profile and a criteria draft concurrently).
    """
    criteria_store = CriteriaStore(store.root)
    profile_store = ProfileStore(store.root)
    test_locks = locks or TestArtifactLocks()
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
