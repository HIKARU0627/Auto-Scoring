"""HTTP boundary for test registration and profile review (Issue #16).

Thin per `AGENTS.md` "Architecture", following the shape
`api.dependency_graph_router` already established: every handler opens one
`SqlAlchemyUnitOfWork` per request, calls into the domain/adapters, and
translates the result to a Pydantic response.

Registration flow (simplified-design-specification.md §6, docs/test-registration.md):

* ``POST /tests`` -- register a new test from its **採点基準PDF** plus any
  optional role-tagged materials (Issue #101). Creates a ``DRAFT`` `Test`;
  no profile exists yet. There is no model-answer parameter any more -- that
  document does not exist in real grading material (Issue #95 decision 1).
* ``GET`` / ``POST /tests/{test_id}/materials`` -- list what was registered
  and under which role, and attach more later.
* ``DELETE /tests/{test_id}`` -- delete a test and everything under it, for
  when a batch was imported into the wrong one.
* ``POST /tests/{test_id}/profile/analyze`` -- generate DRAFT profile
  candidates (`adapters.pdf.profile_candidate_generation`). Safe to call
  again (e.g. after a failed detection) -- it always overwrites whatever
  DRAFT profile was there, exactly like
  `adapters.local.profile_store.ProfileStore.save`. Rejected once the
  profile has been confirmed (a confirmed profile is immutable, matching
  `domain.profile.Profile`'s own one-way DRAFT -> CONFIRMED lifecycle).
  **Needs a model-answer-shaped reference PDF and says so when there is
  none** -- see the handler.
* ``GET /tests/{test_id}/profile`` -- the current (draft or confirmed) profile.
* ``PUT /tests/{test_id}/profile`` -- replace the profile's regions with a
  human-reviewed set (still DRAFT -- this is *not* the confirm step). Lets
  the review screen add/edit/remove regions, including fully manual ones for
  a format automatic detection could not handle.
* ``POST /tests/{test_id}/profile/confirm`` -- the human confirmation step:
  every region must already be ``confirmed=true`` (the caller attests to
  each one, matching `Profile.confirm`'s own contract), and the resulting
  regions are turned into the test's real `Question`/`Rubric` rows
  (`domain.test_registration.build_questions_and_rubrics`). One-way: a
  profile that is already `CONFIRMED` cannot be confirmed again.
* ``POST /tests/{test_id}/complete-registration`` -- the final gate: only
  once both the profile *and* the dependency graph (Issue #26) are confirmed
  does the test move from ``draft`` to ``ready`` (`Test.mark_ready`). This is
  the Issue #16 acceptance criterion "全必須項目確認後にだけ登録完了になる".
"""

from __future__ import annotations

import tempfile
import threading
from asyncio import to_thread
from collections.abc import Iterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.atomic import FinalizationError
from auto_scoring.adapters.image.ink import measure_page_boxes, measure_page_ruling
from auto_scoring.adapters.local.criteria_store import CriteriaStore
from auto_scoring.adapters.local.profile_store import ProfileStore
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.profile_candidate_generation import generate_profile_candidates
from auto_scoring.adapters.purge import purge_test
from auto_scoring.adapters.submission_intake import RENDER_SCALE
from auto_scoring.adapters.test_intake import MaterialUpload, attach_materials, register_test
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.test_artifact_lock import TestArtifactLocks
from auto_scoring.domain.ai_provider import ProviderUnavailable, SchemaViolation
from auto_scoring.domain.answer_area_detection import (
    AnswerAreaDetectionError,
    AnswerAreaDetectionRequest,
    AnswerAreaDetector,
    UnconfiguredAnswerAreaDetector,
    ensure_answer_areas_confirmable,
    missing_question_numbers,
    reading_order_conflicts,
    regions_from_detection,
    unassigned_answer_area_ids,
)
from auto_scoring.domain.criteria_extraction import CriteriaDraft, CriteriaStatus
from auto_scoring.domain.dependency_graph import can_start_submission_processing
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.material_intake import MaterialIntakeError, MaterialTooLargeError
from auto_scoring.domain.models import (
    MAX_ORIGINAL_FILENAME_LENGTH,
    MAX_TEST_NAME_LENGTH,
    MAX_TEST_SUBJECT_LENGTH,
    DomainError,
    Test,
    TestStatus,
)
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_intake import (
    IntakeLimits,
    PdfCorruptedError,
    PdfEncryptedError,
    PdfIntakeError,
    PdfTooLargeError,
    StagedOutputTooLargeError,
    validate_page_count,
    validate_render_dimensions,
    validate_upload_bytes,
)
from auto_scoring.domain.profile import (
    FormatSignature,
    NormalizedBBox,
    PageFormat,
    Profile,
    ProfileStatus,
    Region,
    RegionKind,
)
from auto_scoring.domain.test_material import TestMaterial
from auto_scoring.domain.test_registration import (
    CrossPageRegionError,
    QuestionsInUseError,
    build_questions_and_rubrics,
    ensure_questions_can_be_rebuilt,
)

#: Intake failures that are a size problem, not a content problem, and so
#: deserve 413 rather than 400. Covers both validation families: PDFs go
#: through `domain.pdf_intake`, and the Word/Excel materials Issue #101 added
#: go through `domain.material_intake`, which has no PDF concepts to reuse.
_INTAKE_ERROR_STATUS: dict[type[Exception], int] = {
    PdfTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    StagedOutputTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    MaterialTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
}

#: Read chunk size for `_read_upload_within_limit`, matching `api.app`'s own
#: constant -- bounds how much of an over-limit upload is ever materialized
#: in one `bytes` object before aborting.
_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


async def _read_upload_within_limit(file: UploadFile, max_size_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size_bytes:
            raise PdfTooLargeError(f"file size exceeds limit {max_size_bytes}")
        chunks.append(chunk)
    return b"".join(chunks)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _first_material(materials: Sequence[TestMaterial], role: MaterialRole) -> TestMaterial | None:
    """The oldest material of ``role``, or ``None``.

    Oldest rather than newest so the choice is stable: a test may hold four
    materials of the same role (one real subject folder ships four 添削
    サンプル), and an analysis that silently switched documents when a fifth
    was attached would invalidate regions a reviewer had already positioned.
    """
    for material in materials:
        if material.role is role:
            return material
    return None


def _layout_source_material(materials: Sequence[TestMaterial]) -> TestMaterial | None:
    """The PDF whose page geometry the profile is bound to, if there is one.

    A `REFERENCE` material -- which is where a model answer goes when a
    reviewer happens to have one, and where migration 0015 puts the
    model-answer PDF of every test registered before Issue #101. Restricted
    to PDFs because `generate_profile_candidates` opens it with pdfium, and
    `REFERENCE` also accepts Word/Excel.
    """
    for material in materials:
        if material.role is MaterialRole.REFERENCE and material.stored_path.endswith(".pdf"):
            return material
    return None


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #
class TestResponse(BaseModel):
    id: str
    name: str
    subject: str | None = None
    status: str
    created_at: datetime

    @classmethod
    def from_domain(cls, test: Test) -> TestResponse:
        return cls(
            id=test.id,
            name=test.name,
            subject=test.subject,
            status=test.status.value,
            created_at=test.created_at.replace(tzinfo=UTC),
        )


class TestMaterialResponse(BaseModel):
    """One registered file, and the role it was registered under.

    ``original_filename`` is the name the reviewer chose the file by. It is
    carried purely so "which of my files became the 採点基準?" stays
    answerable after import; nothing matches on it, because names in real
    material are not reliable evidence (`domain.intake_template`).
    """

    id: str
    test_id: str
    role: MaterialRole
    sha256: str
    size_bytes: int
    original_filename: str | None = None
    created_at: datetime

    @classmethod
    def from_domain(cls, material: TestMaterial) -> TestMaterialResponse:
        return cls(
            id=material.id,
            test_id=material.test_id,
            role=material.role,
            sha256=material.sha256,
            size_bytes=material.size_bytes,
            original_filename=material.original_filename,
            created_at=material.created_at.replace(tzinfo=UTC),
        )


class NormalizedBBoxModel(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

    def to_domain(self) -> NormalizedBBox:
        return NormalizedBBox(x0=self.x0, y0=self.y0, x1=self.x1, y1=self.y1)

    @classmethod
    def from_domain(cls, bbox: NormalizedBBox) -> NormalizedBBoxModel:
        return cls(x0=bbox.x0, y0=bbox.y0, x1=bbox.x1, y1=bbox.y1)


class RegionModel(BaseModel):
    region_id: str
    # Typed as the domain enum (not `str`) so Pydantic itself rejects an
    # unknown region kind at request-validation time (422), matching
    # `DependencyEdgeModel.provides` in `api.dependency_graph_router`.
    kind: RegionKind
    page_index: int
    bbox: NormalizedBBoxModel
    label: str
    confirmed: bool = False
    text: str | None = None

    def to_domain(self) -> Region:
        return Region(
            region_id=self.region_id,
            kind=self.kind,
            page_index=self.page_index,
            bbox=self.bbox.to_domain(),
            label=self.label,
            confirmed=self.confirmed,
            text=self.text,
        )

    @classmethod
    def from_domain(cls, region: Region) -> RegionModel:
        return cls(
            region_id=region.region_id,
            kind=region.kind,
            page_index=region.page_index,
            bbox=NormalizedBBoxModel.from_domain(region.bbox),
            label=region.label,
            confirmed=region.confirmed,
            text=region.text,
        )


class PageFormatModel(BaseModel):
    width_pt: float
    height_pt: float

    @classmethod
    def from_domain(cls, page: PageFormat) -> PageFormatModel:
        return cls(width_pt=page.width_pt, height_pt=page.height_pt)


class ProfileResponse(BaseModel):
    test_id: str
    status: str
    pages: list[PageFormatModel]
    regions: list[RegionModel]
    #: Compare-and-set token for `POST /profile/confirm` -- see
    #: `domain.profile.Profile.revision`'s own docstring.
    revision: int
    #: This test's confirmed question numbers, in the order the review screen
    #: should list them (page, then number). Since Issue #105 the 回答欄 editor
    #: assigns each drawn box to one of these -- a dropdown, not a text field,
    #: for the same reason detection itself is a multiple-choice question
    #: (`domain.answer_area_detection`). Empty until the 採点基準 has been
    #: confirmed, which is what makes the questions exist at all.
    question_numbers: list[str]
    #: Questions with no `ANSWER_AREA` region that detection did **not** say
    #: were absent from the sheet: the box should be there and was not found.
    #: **Derived on every response, never stored** -- a stored copy would
    #: still be listing a question as undetected in the one moment it
    #: matters, immediately after the reviewer draws its box. Shown, but does
    #: not block confirming: see `domain.answer_area_detection`'s module
    #: docstring for why this is treated differently from Issue #103's
    #: unknown 配点.
    undetected_question_numbers: list[str]
    #: Questions detection reported as having no answer space anywhere on the
    #: registered sheet (Issue #164). Also has no region, and also does not
    #: block confirming -- but it asks the reviewer for the opposite action:
    #: drawing a box would invent one, and what needs fixing is the 採点基準 or
    #: the registered sheet. Derived from the same region set as
    #: `undetected_question_numbers`, against what detection stored
    #: (`Profile.absent_question_numbers`), so a reviewer who draws the box
    #: anyway drops it out of both lists.
    absent_question_numbers: list[str]
    #: Pairs of question numbers whose boxes sit in the opposite order to
    #: their numbers on the page they share (Issue #171). Advisory: it names
    #: a suspicion, and which of the two boxes is the misplaced one is not
    #: decidable from the geometry -- so it does **not** block confirming,
    #: and nothing is re-labelled automatically. Derived on every response
    #: from the current region set, like every other list here.
    reading_order_conflicts: list[list[str]]
    #: Region ids of detected boxes that still have no question assigned.
    #: These *do* block confirming (`ensure_answer_areas_confirmable`) --
    #: `build_questions_and_rubrics` would ignore them without a word.
    unassigned_region_ids: list[str]

    @classmethod
    def from_domain(cls, profile: Profile, *, question_numbers: Sequence[str]) -> ProfileResponse:
        undetected, absent = missing_question_numbers(
            profile.regions, question_numbers, profile.absent_question_numbers
        )
        return cls(
            test_id=profile.format_id,
            status=profile.status.value,
            pages=[PageFormatModel.from_domain(page) for page in profile.signature.pages],
            regions=[RegionModel.from_domain(region) for region in profile.regions],
            revision=profile.revision,
            question_numbers=list(question_numbers),
            undetected_question_numbers=list(undetected),
            absent_question_numbers=list(absent),
            reading_order_conflicts=[
                list(pair) for pair in reading_order_conflicts(profile.regions, question_numbers)
            ],
            unassigned_region_ids=list(unassigned_answer_area_ids(profile.regions)),
        )


class AnswerLayoutResponse(BaseModel):
    """The reference answer sheet this test's answer areas are laid out
    against (Issue #105), and whether detection can run here at all.
    """

    test_id: str
    #: ``None`` when no answer sheet has been uploaded yet -- distinct from
    #: ``0``, which no PDF has (the same "not run" vs "ran and found nothing"
    #: distinction Issue #103 drew for extraction).
    page_count: int | None
    detection_available: bool
    #: Why detection is unavailable, in terms of configuration *variable
    #: names* only (`adapters.answer_area_detection.factory`). ``None`` when
    #: it is available.
    detection_unavailable_reason: str | None = None
    #: How many existing regions a replacement answer sheet left behind
    #: because their page no longer exists (a 3-page sheet swapped for a
    #: 1-page one). Always ``0`` on `GET`. Reported rather than dropped in
    #: silence -- the coordinates were somebody's work.
    dropped_region_count: int = 0


class UpdateProfileRequest(BaseModel):
    # Required, no default: an empty list must be a deliberate "delete every
    # region" decision, not an accidental omission (same reasoning as
    # `ConfirmRequest.edges` in `api.dependency_graph_router`). A
    # `default_factory=list` here would let a malformed `{}` body silently
    # wipe every region instead of failing validation with 422.
    regions: list[RegionModel]


class ConfirmProfileRequest(BaseModel):
    #: The `revision` the reviewer's client last fetched/saved (`GET`/
    #: `PUT /profile`'s own response) -- must match the profile currently
    #: on disk, or the confirm is rejected as stale (Issue #16 review round
    #: 8; see `domain.profile.Profile.revision`).
    revision: int


class CompleteRegistrationResponse(BaseModel):
    test: TestResponse
    profile_confirmed: bool
    dependency_graph_confirmed: bool


class _AnswerLayoutConfirmedError(Exception):
    """The reference answer sheet cannot be replaced: the profile confirmed
    against it is immutable (Issue #105 review round 1, P2).

    Internal to this module -- `upload_answer_layout` turns it into a 409.
    Raised from inside `_store_answer_layout`, which runs in a worker thread,
    so it must be an exception rather than an `HTTPException` raised there.
    """

    def __init__(self, test_id: str) -> None:
        super().__init__(
            f"test {test_id!r}'s profile is already confirmed; its reference answer sheet "
            "cannot be replaced, because the confirmed answer areas are coordinates on it"
        )


def _intake_http_exception(exc: PdfIntakeError | MaterialIntakeError) -> HTTPException:
    status_code = _INTAKE_ERROR_STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code, detail=str(exc))


def build_test_registration_router(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    pdf_engine: PdfEngine,
    *,
    intake_limits: IntakeLimits | None = None,
    pdfium_lock: threading.Lock | None = None,
    locks: TestArtifactLocks | None = None,
    answer_area_detector: AnswerAreaDetector | None = None,
) -> APIRouter:
    """Build the router. One `SqlAlchemyUnitOfWork` is opened per request.

    ``session_factory`` is the same ``sessionmaker`` `api.app.create_app`
    passes to `api.dependency_graph_router.build_dependency_graph_router`.

    ``pdfium_lock`` must be the *same* lock `api.app.create_app` uses to
    serialize its own answer-intake pipeline (`intake_lock`): pypdfium2 is
    not safe to call concurrently from multiple threads of one process, and
    FastAPI runs each of this router's synchronous handlers in a worker
    thread, so a profile analysis (or PDF validation during registration)
    overlapping with a submission-intake render would otherwise reach
    PDFium from two threads at once. When omitted (e.g. schema export, unit
    tests that never call `analyze`/`create_test` concurrently with intake),
    a private lock is created -- still correct on its own, just not shared
    with the rest of the app.

    ``locks`` must likewise be the same :class:`TestArtifactLocks`
    `api.criteria_router.build_criteria_router` is given: since Issue #103
    that router's ``/criteria/confirm`` rebuilds the very same
    `Question`/`Rubric` rows `confirm_profile` below does, from the very same
    pair of artefacts (`api.test_artifact_lock` spells out the interleave a
    second registry would allow).
    ``answer_area_detector`` is the Issue #105 detection port. Omitted (in
    tests that never call it, and in schema export) it becomes an
    `UnconfiguredAnswerAreaDetector`, so the endpoints still exist and answer
    with a reason -- the screen must be able to open and let a reviewer draw
    the boxes by hand on a host with no image-capable provider.
    """
    limits = intake_limits or IntakeLimits()
    profile_store = ProfileStore(store.root)
    criteria_store = CriteriaStore(store.root)
    lock = pdfium_lock or threading.Lock()
    detector = answer_area_detector or UnconfiguredAnswerAreaDetector(
        "回答欄の自動検出は、このパソコンでは設定されていません。"
        "AUTO_SCORING_AI_GRADING_TRANSPORT に画像を送れる provider を設定してください。"
        "設定しなくても、回答欄は画面上で手動で引けます。"
    )
    router = APIRouter(tags=["test-registration"])

    # `Profile` has no DB row or version -- it is a JSON file that
    # `/profile/analyze`, `PUT /profile`, and `/profile/confirm` each read,
    # transform, and overwrite in full. Without serializing those three per
    # test, an `/analyze` (or `PUT /profile`) that started before a
    # `/confirm` -- but finishes after it committed the confirmed
    # Questions/Rubrics and saved the confirmed profile file -- would
    # overwrite that confirmed file with its own stale DRAFT result, with
    # nothing left on disk to say the test was ever confirmed (Issue #16
    # review round 3). Since Issue #103 the same registry also covers
    # `/criteria/*`, which rebuilds the same rows -- hence a shared object
    # rather than a dict local to this builder.
    test_locks = locks or TestArtifactLocks()

    def _profile_lock(test_id: str) -> threading.Lock:
        return test_locks.for_test(test_id)

    def _uow() -> Iterator[SqlAlchemyUnitOfWork]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            yield uow

    uow_dependency = Depends(_uow)

    def _get_test_or_404(uow: SqlAlchemyUnitOfWork, test_id: str) -> Test:
        test = uow.tests.get(test_id)
        if test is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"test {test_id!r} not found")
        return test

    def _confirmed_criteria(test_id: str) -> CriteriaDraft | None:
        """This test's 採点基準, but only once a human has confirmed it
        (Issue #103).

        `confirm_profile` rebuilds the whole `Question`/`Rubric` set, so
        without this a profile confirmed *after* the criteria would drop
        every point value a reviewer had already signed off on -- the test
        would go back to having no usable score and nothing on screen would
        say why. An unconfirmed draft is deliberately ignored: it is a
        proposal nobody has checked, and folding it in here would be a
        second way to reach the database that bypasses the 不明 gate
        (`domain.criteria_extraction.ensure_confirmable`).
        """
        try:
            draft = criteria_store.load(test_id)
        except FileNotFoundError:
            return None
        return draft if draft.status is CriteriaStatus.CONFIRMED else None

    def _question_numbers(uow: SqlAlchemyUnitOfWork, test_id: str) -> list[str]:
        """This test's confirmed question numbers, in review order.

        The single source of the choices the 回答欄 editor offers and the
        detector is constrained to (Issue #105). Deliberately the `Question`
        rows and not the 採点基準 draft directly: since Issue #103 those rows
        *are* the confirmed draft (``/criteria/confirm`` builds them), and
        reading them keeps this module from importing that Issue's domain at
        all -- so a test registered before it, whose questions came from
        `QUESTION`/`SCORE` regions instead, offers exactly the same choices
        through exactly the same code.

        Empty means "no questions confirmed yet", which is a stop, not a
        default: with nothing to choose from there is no multiple-choice
        question to ask.
        """
        return [question.number for question in uow.questions.list_for_test(test_id)]

    def _load_profile_or_404(test_id: str) -> Profile:
        try:
            return profile_store.load(test_id)
        except FileNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"test {test_id!r} has no profile yet; run /profile/analyze first",
            ) from exc

    def _register_test_locked(
        uow: SqlAlchemyUnitOfWork,
        *,
        name: str,
        subject: str | None,
        materials: list[MaterialUpload],
        now: datetime,
    ) -> tuple[Test, list[TestMaterial]]:
        # Holds `pdfium_lock` for the PDF-validation calls inside
        # register_test (page_count/is_encrypted) -- see
        # build_test_registration_router's docstring for why this must be
        # the same lock the answer-intake pipeline uses.
        with lock:
            return register_test(
                uow,
                store,
                pdf_engine,
                name=name,
                subject=subject,
                materials=materials,
                limits=limits,
                now=now,
            )

    def _attach_materials_locked(
        uow: SqlAlchemyUnitOfWork,
        *,
        test_id: str,
        materials: list[MaterialUpload],
        now: datetime,
    ) -> list[TestMaterial]:
        with lock:
            return attach_materials(
                uow,
                store,
                pdf_engine,
                test_id=test_id,
                materials=materials,
                limits=limits,
                now=now,
            )

    async def _read_materials(uploads: list[UploadFile], roles: list[str]) -> list[MaterialUpload]:
        """Pair each uploaded file with its role, reading it within the limit.

        The two lists are positional: `materials[i]` is the file for
        `material_roles[i]`. A multipart body cannot nest, and inventing a
        JSON side-channel to carry the pairing would mean the roles arrived
        through a different validation path than the files they describe.
        The length check below is what makes the positional pairing safe --
        a mismatched pair would otherwise silently shift every role by one.
        """
        if len(uploads) != len(roles):
            raise HTTPException(
                422,
                detail=(
                    f"materials and material_roles must be the same length, "
                    f"got {len(uploads)} and {len(roles)}"
                ),
            )
        read: list[MaterialUpload] = []
        for upload, raw_role in zip(uploads, roles, strict=True):
            try:
                role = MaterialRole(raw_role)
            except ValueError as exc:
                raise HTTPException(422, detail=f"unknown material role: {raw_role!r}") from exc
            try:
                data = await _read_upload_within_limit(upload, limits.max_size_bytes)
            except PdfIntakeError as exc:
                raise _intake_http_exception(exc) from exc
            read.append(
                MaterialUpload(
                    role=role,
                    filename=(upload.filename or "")[:MAX_ORIGINAL_FILENAME_LENGTH],
                    data=data,
                )
            )
        return read

    @router.post("/tests", response_model=TestResponse, status_code=status.HTTP_201_CREATED)
    async def create_test(
        name: str = Form(...),
        subject: str | None = Form(None),
        criteria: UploadFile = File(...),
        materials: list[UploadFile] = File(default_factory=list),
        material_roles: list[str] = Form(default_factory=list),
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> TestResponse:
        """Register a test from its 採点基準PDF plus any optional materials.

        ``criteria`` is the one required file (Issue #95 decision 1). **There
        is no model-answer parameter**: that document does not exist in real
        grading material, and requiring it is what made this screen unusable.
        A model answer a reviewer happens to have goes in ``materials`` with
        the ``reference`` role like any other extra file.

        Registering does **not** make the test gradable. Points and rubrics
        still have to come from somewhere, and extracting them from the
        criteria PDF is separate work (Issue #95 decision A) -- callers must
        say so rather than implying grading can start.
        """
        if not name.strip():
            raise HTTPException(422, detail="name must not be empty")
        # Cheapest possible rejection, before a single upload byte is read:
        # an authenticated caller could otherwise pack most of the request
        # size limit into these two form fields, which are stored verbatim
        # and returned in full on every registration list response (Issue
        # #16 review round 8; `Test.__post_init__` guarantees the same bound
        # regardless of entry point, this just fails faster here).
        if len(name) > MAX_TEST_NAME_LENGTH:
            raise HTTPException(
                422, detail=f"name must be at most {MAX_TEST_NAME_LENGTH} characters"
            )
        if subject is not None and len(subject) > MAX_TEST_SUBJECT_LENGTH:
            raise HTTPException(
                422, detail=f"subject must be at most {MAX_TEST_SUBJECT_LENGTH} characters"
            )

        uploads = await _read_materials(materials, material_roles)
        try:
            criteria_data = await _read_upload_within_limit(criteria, limits.max_size_bytes)
        except PdfIntakeError as exc:
            raise _intake_http_exception(exc) from exc
        all_materials = [
            MaterialUpload(
                role=MaterialRole.GRADING_CRITERIA,
                filename=(criteria.filename or "")[:MAX_ORIGINAL_FILENAME_LENGTH],
                data=criteria_data,
            ),
            *uploads,
        ]

        try:
            # PDF parsing/validation and the DB+file write are synchronous,
            # blocking work that can take a while for a large PDF; running
            # it inline here would stall this whole (single-worker) event
            # loop -- even /healthz -- for as long as it (or a submission
            # intake holding the same `lock`) takes (Issue #16 review, same
            # reasoning as api.app.create_app's own `_run_intake`). Offload
            # it to a worker thread instead.
            test, _ = await to_thread(
                _register_test_locked,
                uow,
                name=name,
                subject=subject,
                materials=all_materials,
                now=_now(),
            )
        except (PdfIntakeError, MaterialIntakeError) as exc:
            raise _intake_http_exception(exc) from exc
        except FinalizationError as exc:
            # The Test row was compensated away (register_test's own
            # handling) -- report a retryable failure rather than a 500
            # that suggests the id survived when it didn't.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"could not save the registered files to disk: {exc}",
            ) from exc
        return TestResponse.from_domain(test)

    @router.get("/tests/{test_id}/materials", response_model=list[TestMaterialResponse])
    def list_materials(
        test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> list[TestMaterialResponse]:
        """Which file became which role for this test.

        The answer to "did my 採点基準 actually land as the 採点基準?", which
        is only answerable after import if the name the reviewer chose the
        file by survives -- so `original_filename` is carried through.
        """
        _get_test_or_404(uow, test_id)
        return [
            TestMaterialResponse.from_domain(material)
            for material in uow.test_materials.list_for_test(test_id)
        ]

    @router.post(
        "/tests/{test_id}/materials",
        response_model=list[TestMaterialResponse],
        status_code=status.HTTP_201_CREATED,
    )
    async def add_materials(
        test_id: str,
        materials: list[UploadFile] = File(...),
        material_roles: list[str] = Form(...),
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> list[TestMaterialResponse]:
        """Attach more materials to a test that already exists.

        The weekly flow needs this in both directions: answers for an
        already-registered test arrive as submissions, and a 添削資料 that
        turns up later must be attachable without re-registering the test.

        Re-sending a file already attached under the same role returns the
        existing material instead of a second copy, so retrying a batch that
        failed part-way through is safe (Issue #101: 成功した分は残る).
        """
        _get_test_or_404(uow, test_id)
        uploads = await _read_materials(materials, material_roles)
        try:
            attached = await to_thread(
                _attach_materials_locked,
                uow,
                test_id=test_id,
                materials=uploads,
                now=_now(),
            )
        except (PdfIntakeError, MaterialIntakeError) as exc:
            raise _intake_http_exception(exc) from exc
        except FinalizationError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"could not save the attached files to disk: {exc}",
            ) from exc
        return [TestMaterialResponse.from_domain(material) for material in attached]

    @router.delete("/tests/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_test(test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency) -> Response:
        """Delete a test and everything under it.

        Exposed because importing into the wrong test is an ordinary mistake,
        not an exotic one: the reviewer finds out after the fact, and without
        this the only remedy would be editing `app-data/` by hand. The bulk
        delete itself already existed (`adapters.purge.purge_test`: rows
        cascade, files are removed, and the deletion is written to the audit
        log per business-rules §2 (11)) -- it simply had no HTTP route.
        """
        _get_test_or_404(uow, test_id)
        purge_test(uow, store, test_id=test_id, occurred_at=_now(), detail="deleted via API")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/test-registrations", response_model=list[TestResponse])
    def list_test_registrations(uow: SqlAlchemyUnitOfWork = uow_dependency) -> list[TestResponse]:
        """Every test regardless of status (draft or ready), for the テスト
        設定画面's own entry point.

        `GET /tests` (api.app, answer intake's test picker) only returns
        `ready` tests -- a `draft` test has no other way to be found again
        once its `TestSettingsPage` is closed (Issue #16 review: leaving
        registration mid-way, or restarting the app, must not make an
        already-uploaded, persisted draft unreachable).
        """
        return [TestResponse.from_domain(test) for test in uow.tests.list_all()]

    @router.get("/tests/{test_id}", response_model=TestResponse)
    def get_test(test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency) -> TestResponse:
        return TestResponse.from_domain(_get_test_or_404(uow, test_id))

    @router.post("/tests/{test_id}/profile/analyze", response_model=ProfileResponse)
    def analyze_profile(
        test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> ProfileResponse:
        _get_test_or_404(uow, test_id)
        # Serializes against `update_profile`/`confirm_profile` for this
        # same test -- see `_profile_lock`'s docstring.
        with _profile_lock(test_id):
            try:
                existing = profile_store.load(test_id)
            except FileNotFoundError:
                existing = None
            if existing is not None and existing.status is ProfileStatus.CONFIRMED:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=(
                        f"test {test_id!r}'s profile is already confirmed and cannot be re-analyzed"
                    ),
                )

            materials = uow.test_materials.list_for_test(test_id)
            layout_source = _layout_source_material(materials)
            criteria = _first_material(materials, MaterialRole.GRADING_CRITERIA)
            if layout_source is None or criteria is None:
                # Automatic candidate generation reads *two* documents: it
                # takes the page geometry (the profile's `FormatSignature`,
                # which submissions are later matched against) from a
                # model-answer-shaped PDF, and only the rubric/score text
                # from the criteria PDF. Issue #101 made the model answer
                # optional because it does not exist in real material --
                # which means this analysis frequently has nothing to derive
                # a layout from.
                #
                # Deriving the layout from the answers instead is what Issue
                # #105 added, and it is now the normal path: `PUT
                # /answer-layout` + `/answer-layout/detect` take the page
                # geometry from a real answer sheet, which every test has.
                # This endpoint stays for tests that *do* carry a
                # reference PDF (migration 0015 gives every pre-Issue-#101
                # test one), and says where to go otherwise.
                #
                # Silently analysing the criteria PDF's own geometry instead
                # would produce a profile bound to a page layout no
                # submission has, and every later crop would be taken from
                # the wrong coordinates.
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=(
                        "この解析には、回答欄の位置が分かる参考資料 (模範解答PDF など) が"
                        "必要です。この教材には登録されていません。"
                        "回答欄は答案そのものから決めてください。"
                        "答案を取り込んで「回答欄を自動検出」するか、画面上で手動追加できます。"
                    ),
                )
            try:
                # Same `pdfium_lock` register_test uses above -- see
                # build_test_registration_router's docstring. FastAPI runs
                # this synchronous handler in a worker thread, so without
                # this an analysis overlapping another analysis or a
                # submission-intake render would reach PDFium from two
                # threads at once.
                with lock:
                    profile = generate_profile_candidates(
                        pdf_engine,
                        test_id,
                        test_id,
                        store.resolve_stored_path(layout_source.stored_path),
                        store.resolve_stored_path(criteria.stored_path),
                    )
            except FileNotFoundError as exc:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=(
                        f"test {test_id!r}'s registered files are missing on disk; "
                        "re-attach them before analysing"
                    ),
                ) from exc
            except PdfIntakeError as exc:
                raise _intake_http_exception(exc) from exc
            except DomainError as exc:
                raise HTTPException(422, detail=str(exc)) from exc

            # Bumped, not reset to 1: a fresh analysis is still a change to
            # the region set a reviewer may have already fetched/reviewed
            # at the previous revision, and must invalidate a confirm
            # pinned to that revision the same way `PUT /profile` below
            # does (Issue #16 review round 8).
            profile = replace(profile, revision=(existing.revision + 1 if existing else 1))
            profile_store.save(profile)
        return ProfileResponse.from_domain(
            profile, question_numbers=_question_numbers(uow, test_id)
        )

    @router.get("/tests/{test_id}/profile", response_model=ProfileResponse)
    def get_profile(test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency) -> ProfileResponse:
        _get_test_or_404(uow, test_id)
        return ProfileResponse.from_domain(
            _load_profile_or_404(test_id), question_numbers=_question_numbers(uow, test_id)
        )

    @router.put("/tests/{test_id}/profile", response_model=ProfileResponse)
    def update_profile(
        test_id: str, request: UpdateProfileRequest, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> ProfileResponse:
        _get_test_or_404(uow, test_id)
        # Serializes against `analyze_profile`/`confirm_profile` for this
        # same test -- see `_profile_lock`'s docstring.
        with _profile_lock(test_id):
            existing = _load_profile_or_404(test_id)
            if existing.status is ProfileStatus.CONFIRMED:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=f"test {test_id!r}'s profile is already confirmed and cannot be edited",
                )
            try:
                updated = Profile.from_candidates(
                    existing.profile_id,
                    existing.format_id,
                    existing.signature,
                    [region.to_domain() for region in request.regions],
                )
            except ValueError as exc:
                raise HTTPException(422, detail=str(exc)) from exc
            # Bumped from whatever the currently-saved profile was at, not
            # reset to 1 -- see `Profile.revision`'s docstring and
            # `analyze_profile`'s matching comment above.
            updated = replace(updated, revision=existing.revision + 1)
            profile_store.save(updated)
        return ProfileResponse.from_domain(
            updated, question_numbers=_question_numbers(uow, test_id)
        )

    @router.post("/tests/{test_id}/profile/confirm", response_model=ProfileResponse)
    def confirm_profile(
        test_id: str,
        request: ConfirmProfileRequest,
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> ProfileResponse:
        test = _get_test_or_404(uow, test_id)
        # Serializes against `analyze_profile`/`update_profile` for this
        # same test -- see `_profile_lock`'s docstring.
        with _profile_lock(test_id):
            profile = _load_profile_or_404(test_id)
            if profile.status is ProfileStatus.CONFIRMED:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=f"test {test_id!r}'s profile is already confirmed",
                )
            if profile.revision != request.revision:
                # Confirming attests to "the region set I reviewed", not
                # "whatever happens to be on disk right now" -- without
                # this, another client's `PUT /profile` or `/analyze`
                # landing between this reviewer's own save and their
                # confirm call (the per-test lock only serializes
                # individual requests against each other, it doesn't stop
                # a *later* request from legitimately changing the profile
                # first) would have this confirm silently approve regions
                # nobody actually reviewed under this attestation (Issue
                # #16 review round 8, docs/test-registration.md's
                # human-review contract).
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=(
                        f"test {test_id!r}'s profile has changed since revision "
                        f"{request.revision} was reviewed (current revision: "
                        f"{profile.revision}); reload and re-review before confirming"
                    ),
                )
            if not profile.regions:
                raise HTTPException(
                    422, detail=f"test {test_id!r}'s profile has no regions to confirm"
                )
            try:
                # A detected box nobody attributed to a question would be
                # dropped in silence by `build_questions_and_rubrics` (which
                # ignores a label no question claims). Stopping here turns
                # that silence into something the reviewer can act on:
                # assign it, or delete it (Issue #105 acceptance 4).
                ensure_answer_areas_confirmable(profile.regions)
            except AnswerAreaDetectionError as exc:
                raise HTTPException(422, detail=str(exc)) from exc
            # Confirming is the single act of human sign-off over the whole
            # current region set (there is no per-region "confirmed"
            # checkbox in the review UI -- `Profile.__post_init__` itself
            # forbids a DRAFT profile from holding any `confirmed=true`
            # region, so individual regions never carry that flag before
            # this point). Every region is therefore marked confirmed here,
            # matching `Profile.confirm`'s own contract that the caller
            # attests to each one.
            reviewed_regions = [replace(region, confirmed=True) for region in profile.regions]
            try:
                confirmed = profile.confirm(reviewed_regions)
            except ValueError as exc:
                raise HTTPException(422, detail=str(exc)) from exc

            # Unreachable today -- a submission needs the test READY, READY
            # needs a confirmed profile, and re-confirming one is a 409 above
            # -- so this path is safe by a chain of coincidences elsewhere
            # rather than by a rule of its own. Issue #103's review found the
            # other rebuild path where that chain does not exist; stating the
            # rule here too means neither path depends on the coincidence
            # holding after the next lifecycle change.
            try:
                ensure_questions_can_be_rebuilt(
                    test_id=test_id,
                    submission_count=len(uow.submissions.list_for_test(test_id)),
                )
            except QuestionsInUseError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
            try:
                questions, rubrics = build_questions_and_rubrics(
                    test_id,
                    confirmed.regions,
                    default_scoring_method=test.default_scoring_method,
                    criteria=_confirmed_criteria(test_id),
                )
            except CrossPageRegionError as exc:
                # Measured, not hypothetical: one of the 11 real subjects
                # prints a single question's answer space across two pages
                # ("その1"/"その2"). `Question` holds one page and one rect,
                # so this app genuinely cannot represent that question yet
                # (docs/answer-area-detection.md; its own Issue). Detection
                # deliberately reports the areas on *both* pages rather than
                # dropping half a student's answer -- which means the
                # reviewer meets this error, and it has to say what is wrong
                # and what to do, not just restate the invariant.
                # Issue #215: forewarn that deleting one page's area means only
                # the remaining page will be graded, and if a page is left with
                # no questions, imported answer sheets will be flagged with
                # extra_pages and will not start automated grading.
                raise HTTPException(
                    422,
                    detail=(
                        f"{exc} —— この設問の回答欄が複数ページにまたがっています。"
                        "いまは1設問につき1ページ分しか扱えません。"
                        "どちらか一方のページの回答欄だけを残して確定できますが、"
                        "残したページの分しか採点されません。"
                        "また、設問のないページが生じると、答案取込時にページ超過（extra_pages）"
                        "と判定され、自動採点は開始されず人による確認が必要になります。"
                    ),
                ) from exc
            except DomainError as exc:
                # `build_questions_and_rubrics` raises `TestRegistrationError`
                # for a business-rule violation (duplicate number, bad
                # score, ...), but a malformed region (e.g. a blank question
                # label) only fails once `Question(...)` itself validates
                # it, raising the broader `DomainError` -- catching only the
                # narrower type let that case fall through as an unhandled
                # 500 (Issue #16 review).
                raise HTTPException(422, detail=str(exc)) from exc

            # Reconcile, not insert-if-missing: a retry after a prior
            # confirm attempt that committed the DB write but then failed on
            # profile_store.save() below (DB succeeded, file didn't) must
            # end up with *exactly* this question/rubric set, not a stale
            # one left over from an earlier attempt -- e.g. a since-removed
            # question, or one whose points/areas/model_answer changed,
            # would otherwise keep its old row forever (Issue #16 review: a
            # `ready` test would then be graded against data that no longer
            # matches its confirmed profile). Deleting and rebuilding is
            # safe here: this handler already rejects confirming an
            # already-CONFIRMED profile above, so no downstream submission
            # processing can have started against these rows yet.
            uow.questions.delete_for_test(test_id)
            for question in questions:
                uow.questions.add(question)
            for rubric in rubrics:
                uow.rubrics.add(rubric)
            uow.commit()

            # If this fails (e.g. disk full), the Question/Rubric rows above
            # are already durably committed and this whole handler can
            # simply be retried -- the idempotent write above will skip
            # them, and only the file write needs to succeed the second
            # time.
            profile_store.save(confirmed)
        return ProfileResponse.from_domain(
            confirmed, question_numbers=_question_numbers(uow, test_id)
        )

    @router.post(
        "/tests/{test_id}/complete-registration", response_model=CompleteRegistrationResponse
    )
    def complete_registration(
        test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> CompleteRegistrationResponse:
        test = _get_test_or_404(uow, test_id)
        if test.status is TestStatus.READY:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail=f"test {test_id!r} is already ready"
            )

        try:
            profile = profile_store.load(test_id)
            profile_confirmed = profile.status is ProfileStatus.CONFIRMED
        except FileNotFoundError:
            profile_confirmed = False

        # `get_latest_confirmed(...) is not None` alone is not enough: a
        # confirmed graph is immutable, but the test's own Questions are
        # not -- `confirm_profile`'s reconcile-on-retry can replace them
        # after a graph was already confirmed against the old set, leaving
        # a graph whose `question_ids` no longer describes the test yet
        # still reads CONFIRMED forever. Reuse the same
        # `can_start_submission_processing` gate Issue #26's submission
        # pipeline uses for this exact reason (docs/dependency-graph.md:
        # "CONFIRMEDだけでは不十分") -- marking a test `ready` on top of a
        # stale graph would let submission processing start against
        # question dependencies that never matched the confirmed profile
        # (Issue #16 review round 3).
        latest_confirmed_graph = uow.dependency_graphs.get_latest_confirmed(test_id)
        current_question_ids = {question.id for question in uow.questions.list_for_test(test_id)}
        dependency_graph_confirmed = can_start_submission_processing(
            latest_confirmed_graph,
            current_question_ids=current_question_ids,
            active_confirmed_version=(
                latest_confirmed_graph.version if latest_confirmed_graph is not None else None
            ),
        )

        if not profile_confirmed or not dependency_graph_confirmed:
            missing = []
            if not profile_confirmed:
                missing.append("プロファイル未確認")
            if not dependency_graph_confirmed:
                missing.append("設問依存関係グラフ未確認")
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"test {test_id!r} cannot be marked ready yet: {', '.join(missing)}",
            )

        if not uow.tests.mark_ready(test_id):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"test {test_id!r} could not be marked ready (already changed concurrently)",
            )
        uow.commit()
        ready_test = uow.tests.get(test_id)
        assert ready_test is not None  # just marked ready above, in the same transaction
        return CompleteRegistrationResponse(
            test=TestResponse.from_domain(ready_test),
            profile_confirmed=profile_confirmed,
            dependency_graph_confirmed=dependency_graph_confirmed,
        )

    # ----------------------------------------------------------------- #
    # 回答欄 (Issue #105)
    # ----------------------------------------------------------------- #
    def _validated_signature(data: bytes) -> FormatSignature:
        """Parse one uploaded answer sheet in a scratch directory and return
        the format its pages describe.

        Raises `PdfIntakeError` without touching anything stored: a corrupt or
        absurdly-sized upload must not destroy the sheet the current answer
        areas were drawn on, and must not be discovered later by an
        out-of-memory render inside `/detect`.
        """
        with tempfile.TemporaryDirectory(prefix="auto-scoring-answer-layout-") as scratch_dir:
            scratch = Path(scratch_dir) / "upload.pdf"
            scratch.write_bytes(data)
            # Holds the same `pdfium_lock` every other PDFium call in this
            # process holds -- see `build_test_registration_router`'s docstring.
            with lock:
                try:
                    page_count = pdf_engine.page_count(scratch)
                except Exception as exc:
                    raise PdfCorruptedError(f"could not parse PDF: {exc}") from exc
                if pdf_engine.is_encrypted(scratch):
                    raise PdfEncryptedError("the answer sheet PDF is password protected")
                validate_page_count(page_count, limits)
                geometries = []
                for index in range(page_count):
                    try:
                        geometry = pdf_engine.page_geometry(scratch, index)
                    except Exception as exc:
                        raise PdfCorruptedError(f"could not parse PDF: {exc}") from exc
                    # A tiny PDF can declare an enormous CropBox; `/detect`
                    # rasterizes every page at RENDER_SCALE, so an absurd
                    # declared size is rejected here rather than discovered
                    # as an out-of-memory crash there.
                    validate_render_dimensions(
                        geometry.displayed_width * RENDER_SCALE,
                        geometry.displayed_height * RENDER_SCALE,
                        limits,
                    )
                    geometries.append(geometry)
        return FormatSignature(
            pages=tuple(
                PageFormat(width_pt=g.displayed_width, height_pt=g.displayed_height)
                for g in geometries
            )
        )

    def _store_answer_layout(test_id: str, data: bytes) -> int:
        """Commit one answer sheet as this test's layout reference and bring
        the profile into line with it. Returns how many regions were dropped.

        **The sheet and the profile are one artefact, so they move together.**
        The profile's regions are coordinates *on this sheet*; swapping the
        sheet changes what every one of them means. So this runs under the
        same per-test lock as `/detect` and `PUT /profile`, bumps `revision`
        (a confirm pinned to a revision reviewed against the *old* sheet is
        then rejected as stale), and refuses outright once the profile is
        confirmed -- without which another client could swap the sheet under
        a reviewer mid-review, or change the sheet a finished test was
        confirmed against (Issue #105 review round 1, P2).

        It also *creates* the profile when there is none. That is what makes
        the manual path reachable at all: a test registered without a
        model-answer PDF has no profile, and with no profile there is no
        page format to draw a region on -- so "領域を手動追加" had nothing to
        add to (Issue #105 review round 1, P1). Uploading the sheet is
        precisely the act of saying which document the coordinates are for.
        """
        signature = _validated_signature(data)
        with _profile_lock(test_id):
            try:
                existing: Profile | None = profile_store.load(test_id)
            except FileNotFoundError:
                existing = None
            if existing is not None and existing.status is ProfileStatus.CONFIRMED:
                raise _AnswerLayoutConfirmedError(test_id)

            # Regions on a page the new sheet does not have cannot be
            # reinterpreted -- but they are reported rather than dropped in
            # silence, because they were somebody's work.
            kept = [
                region
                for region in (existing.regions if existing else ())
                if region.page_index < len(signature.pages)
            ]
            dropped = (len(existing.regions) if existing else 0) - len(kept)

            store.write_atomic(store.test_answer_layout_pdf_path(test_id), data)
            profile = Profile.from_candidates(test_id, test_id, signature, kept)
            profile_store.save(
                replace(profile, revision=(existing.revision + 1 if existing else 1))
            )
        return dropped

    def _answer_layout_response(test_id: str, *, dropped: int = 0) -> AnswerLayoutResponse:
        path = store.test_answer_layout_pdf_path(test_id)
        page_count: int | None = None
        if path.exists():
            with lock:
                page_count = pdf_engine.page_count(path)
        unavailable = getattr(detector, "reason", None)
        return AnswerLayoutResponse(
            test_id=test_id,
            page_count=page_count,
            detection_available=unavailable is None,
            detection_unavailable_reason=unavailable,
            dropped_region_count=dropped,
        )

    @router.get("/tests/{test_id}/answer-layout", response_model=AnswerLayoutResponse)
    def get_answer_layout(
        test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> AnswerLayoutResponse:
        """Whether a reference answer sheet is stored, and whether detection
        can run on this host.

        The screen asks this first so it can say *why* the 自動検出 button is
        disabled -- an unconfigured provider and a missing answer sheet are
        different problems with different fixes, and the reviewer can draw
        the boxes by hand in either case.
        """
        _get_test_or_404(uow, test_id)
        try:
            return _answer_layout_response(test_id)
        except Exception as exc:
            # A stored answer sheet that no longer parses must not make the
            # whole settings screen unopenable; it is re-uploadable.
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"the stored answer sheet could not be read: {type(exc).__name__}",
            ) from None

    @router.put("/tests/{test_id}/answer-layout", response_model=AnswerLayoutResponse)
    async def upload_answer_layout(
        test_id: str,
        file: UploadFile = File(...),
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> AnswerLayoutResponse:
        """Store one student's answer sheet as the layout reference for this
        test (Issue #105).

        ``PUT``, not ``POST``: there is exactly one per test and re-uploading
        replaces it. Kept separate from ``/detect`` so a provider failure --
        the common case, since detection is one long multimodal call -- can be
        retried without asking the reviewer for the file again.

        This is not a submission. It gets no `Submission` row and is never
        graded; it exists because the boxes have to be drawn on *something*,
        and a test cannot accept real submissions until they are drawn
        (`adapters.submission_intake.intake_submission` refuses a test that is
        not ``ready``).

        Fully validated -- including per-page render size -- *before* it
        replaces whatever is already stored, in a scratch directory the same
        way `intake_submission` does it. A corrupt or absurdly-sized upload
        must not destroy the sheet the current answer areas were drawn on,
        and must not be discovered later by an out-of-memory render inside
        `/detect`.
        """
        _get_test_or_404(uow, test_id)
        try:
            data = await _read_upload_within_limit(file, limits.max_size_bytes)
            validate_upload_bytes(
                filename=file.filename or "",
                declared_mime=file.content_type,
                data=data,
                limits=limits,
            )
            dropped = await to_thread(_store_answer_layout, test_id, data)
        except _AnswerLayoutConfirmedError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except PdfIntakeError as exc:
            raise _intake_http_exception(exc) from exc
        except OSError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"could not save the answer sheet to disk: {exc}",
            ) from exc
        return _answer_layout_response(test_id, dropped=dropped)

    @router.get(
        "/tests/{test_id}/answer-layout/pdf",
        response_class=Response,
        responses={
            200: {
                "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
                "description": "The reference answer sheet this test's answer areas are drawn on.",
            }
        },
    )
    def get_answer_layout_pdf(test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency) -> Response:
        """The stored answer sheet's raw bytes.

        **Used by the Flutter answer-area editor until the Electron
        cut-over**, and by nothing else. It renders the PDF itself with
        `pdfrx` and places normalized overlays on the result
        (`features/pdf_review`).

        This endpoint used to justify itself with that rendering path -- "the
        app already renders PDFs with pdfrx, so serving pictures would mean a
        second rendering path and a second set of coordinate bugs". **Issue
        #201 removes that premise**: Electron has no `pdfrx`, and PoC 6
        (`docs/poc-6-pdf-coordinates.md`) chose the opposite arrangement --
        the sidecar rasterizes and the renderer displays the picture, so there
        is exactly one rendering path and it is the one that also does the
        coordinate transform. The new UI uses
        `api.page_image_router` (``GET /tests/{test_id}/answer-layout/pages``
        and ``.../pages/{page_index}/image``) and **never receives raw PDF
        bytes**: app-data stays owned by the sidecar.

        **After the cut-over there is no known caller left.** Nothing outside
        the Flutter app reads it: answer-area detection, criteria extraction
        and PDF export all open the stored file directly. It is kept rather
        than deleted here only because the Flutter app still runs.

        **Whether to delete this endpoint (and
        ``GET /submissions/{submission_id}/source-pdf``, kept for the same
        reason) is decided at cut-over, tracked in Issue #201.** There is no
        separate cut-over Issue yet; when one is split out, move the item and
        update this reference. Leaving a reason behind that has stopped being
        true is the failure this repository has repeated (#111 -> #138).
        """
        _get_test_or_404(uow, test_id)
        path = store.test_answer_layout_pdf_path(test_id)
        if not path.exists():
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"test {test_id!r} has no answer sheet uploaded yet",
            )
        return Response(content=store.read_bytes(path), media_type="application/pdf")

    @router.post("/tests/{test_id}/answer-layout/detect", response_model=ProfileResponse)
    def detect_answer_areas(
        test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> ProfileResponse:
        """Detect this test's answer areas on the stored answer sheet and save
        them as DRAFT profile regions (Issue #105).

        Safe to call again -- like `analyze_profile`, it overwrites whatever
        DRAFT profile was there and bumps `revision` so a confirm pinned to
        the previous one is rejected. Refused once the profile is confirmed.

        **Every page goes to the provider, once per test.** Grading sends one
        cropped answer per question per submission; this sends whole pages,
        and only here (simplified-design-specification.md §26.1.1). Whatever
        is printed or handwritten on those pages goes with them.
        """
        _get_test_or_404(uow, test_id)
        numbers = _question_numbers(uow, test_id)
        if not numbers:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"test {test_id!r} has no confirmed questions yet; confirm its 配点と採点基準 "
                    "first, so each detected answer area can be assigned to one of them"
                ),
            )
        source = store.test_answer_layout_pdf_path(test_id)
        if not source.exists():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"test {test_id!r} has no answer sheet to detect answer areas on",
            )

        # Serializes against `analyze_profile`/`update_profile`/
        # `confirm_profile` for this same test -- see `_profile_lock`.
        with _profile_lock(test_id):
            try:
                existing: Profile | None = profile_store.load(test_id)
            except FileNotFoundError:
                existing = None
            if existing is not None and existing.status is ProfileStatus.CONFIRMED:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=(
                        f"test {test_id!r}'s profile is already confirmed and cannot be re-detected"
                    ),
                )

            try:
                # Same `pdfium_lock` the rest of this router and the intake
                # pipeline use: pypdfium2 is not safe to call concurrently
                # from several threads of one process.
                # Every page, at the same rasterization scale the answer-area
                # crop itself uses -- so what the model is shown and what the
                # grader will later be sent come from one rendering, not two.
                # Size/encryption/page-count were all checked at upload.
                with lock:
                    page_count = pdf_engine.page_count(source)
                    geometries = [
                        pdf_engine.page_geometry(source, index) for index in range(page_count)
                    ]
                    page_images = tuple(
                        pdf_engine.render_page_png(source, index, scale=RENDER_SCALE)
                        for index in range(page_count)
                    )
                # Measured from the very images being sent, so the model is
                # choosing among lines it can actually see and the snap
                # afterwards lands on the same values (Issue #122). Outside
                # the pdfium lock: this is OpenCV over bytes already in hand.
                page_rulings = tuple(measure_page_ruling(image) for image in page_images)
                page_boxes = tuple(measure_page_boxes(image) for image in page_images)
            except Exception as exc:
                raise HTTPException(
                    422, detail=f"could not read the stored answer sheet: {type(exc).__name__}"
                ) from None

            signature = FormatSignature(
                pages=tuple(
                    PageFormat(width_pt=g.displayed_width, height_pt=g.displayed_height)
                    for g in geometries
                )
            )

            try:
                output = detector.detect(
                    AnswerAreaDetectionRequest(
                        page_images=page_images,
                        question_numbers=tuple(numbers),
                        page_rulings=page_rulings,
                        page_boxes=page_boxes,
                    )
                )
            except SchemaViolation as exc:
                # Nothing is saved. A partial region set looks exactly like a
                # complete one on the overlay, so half a detection is worse
                # than none (Issue #105 acceptance 5).
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None
            except ProviderUnavailable as exc:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None
            except AnswerAreaDetectionError as exc:
                # `UnconfiguredAnswerAreaDetector`, or a request this host
                # could not even build. Its message names configuration
                # variables only.
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None

            # A profile whose signature describes a *different* document (a
            # legacy one built from the model-answer PDF, before Issue #105)
            # holds regions whose coordinates mean nothing on this answer
            # sheet, so it is replaced outright rather than partly carried
            # over. When the signature matches, the reviewer's own non-
            # answer-area regions survive re-running detection -- which is a
            # normal thing to do after a provider failure.
            carried = (
                existing.regions
                if existing is not None and existing.signature.matches(signature)
                else ()
            )
            try:
                profile = Profile.from_candidates(
                    test_id,
                    test_id,
                    signature,
                    regions_from_detection(
                        output,
                        existing_regions=carried,
                        page_rulings=page_rulings,
                        page_boxes=page_boxes,
                    ),
                    # Replaced outright, never merged with a previous run's:
                    # this is what *this* response said about *these* pages,
                    # and a question the previous run called absent may be one
                    # this run found.
                    absent_question_numbers=output.questions_not_on_these_pages,
                )
            except ValueError as exc:
                raise HTTPException(422, detail=str(exc)) from exc
            profile = replace(profile, revision=(existing.revision + 1 if existing else 1))
            profile_store.save(profile)
        return ProfileResponse.from_domain(profile, question_numbers=numbers)

    return router
