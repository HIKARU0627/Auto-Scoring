"""Integration tests for adapters.submission_intake.intake_submission.

Exercises the full pipeline against a real on-disk SQLite DB and a real
``LocalFileStore``, with the real ``PdfiumPypdfEngine`` / ``OpenCvImagePreprocessor``
adapters -- this is the "複数page/回転/破損/oversize/重複PDFを含む
integration test" Issue #17 asks for.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from auto_scoring.adapters.atomic import FinalizationError
from auto_scoring.adapters.image.opencv_preprocessor import OpenCvImagePreprocessor
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf import PdfiumPypdfEngine
from auto_scoring.adapters.sqlalchemy_repositories import SqlAlchemySubmissionRepository
from auto_scoring.adapters.submission_intake import (
    DuplicateSubmissionError,
    SubmissionRetryConflictError,
    intake_submission,
    repair_incomplete_submissions,
)
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import (
    AnswerImageStatus,
    NormalizedRect,
    Question,
    SubmissionState,
    TestStatus,
)
from auto_scoring.domain.pdf_engine import AnnotationMark, PdfEngine
from auto_scoring.domain.pdf_geometry import NormalizedPoint, PageGeometry
from auto_scoring.domain.pdf_intake import (
    IntakeLimits,
    PdfCorruptedError,
    PdfEncryptedError,
    PdfInvalidTypeError,
    PdfPageLimitExceededError,
    PdfPageTooLargeError,
    StagedOutputTooLargeError,
)
from auto_scoring.domain.submission_intake import READING_ORDER_CONFLICT_REASON
from tests.support import at, make_job, make_question, make_test, written_on_pdf_bytes

_ENGINE = PdfiumPypdfEngine()
_PREPROCESSOR = OpenCvImagePreprocessor()
_LIMITS = IntakeLimits(max_size_bytes=10 * 1024 * 1024, max_pages=20)


def _pdf_bytes(*, pages: int = 1, width: float = 300, height: float = 400) -> bytes:
    """An answer sheet with writing on it.

    Not `PdfWriter.add_blank_page`: since Issue #122 a crop with no ink in it
    is refused rather than graded, so a blank fixture exercises the tripwire
    instead of the happy path these tests are about. `test_nearly_blank`
    below covers the blank sheet deliberately.
    """
    return written_on_pdf_bytes(pages=pages, width=width, height=height)


def _encrypted_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    writer.encrypt(user_password="secret")
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _seed_test_with_questions(
    make_uow: Callable[[], SqlAlchemyUnitOfWork],
    *,
    test_id: str = "test-1",
    questions: list[Question] | None = None,
) -> None:
    with make_uow() as uow:
        # READY: intake_submission() now rejects a draft test (Issue #16) --
        # these tests exercise intake itself, not the registration gate.
        uow.tests.add(make_test(id=test_id, status=TestStatus.READY))
        for question in questions or []:
            uow.questions.add(question)
        uow.commit()


def test_happy_path_creates_submission_and_ok_answer_images(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """Issue #17 acceptance: a 3+ page fixture with every Question correctly
    associated to its own page, in page order -- not just a 2-page fixture
    plus an assertion in prose that a 3rd page "would" follow the same path
    (docs/answer-intake-and-preprocessing.md §12).
    """
    q1 = make_question(
        id="q-1",
        page=1,
        answer_area=NormalizedRect(x=0.1, y=0.1, width=0.5, height=0.2),
    )
    q2 = make_question(
        id="q-2",
        number="問2",
        page=2,
        answer_area=NormalizedRect(x=0.2, y=0.3, width=0.4, height=0.3),
    )
    q3 = make_question(
        id="q-3",
        number="問3",
        page=3,
        answer_area=NormalizedRect(x=0.15, y=0.2, width=0.3, height=0.25),
    )
    _seed_test_with_questions(make_uow, questions=[q1, q2, q3])
    data = _pdf_bytes(pages=3)

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="student-a.pdf",
            declared_mime="application/pdf",
            data=data,
            student_label="student-a",
            limits=_LIMITS,
            now=at(),
        )

    assert result.is_retry is False
    assert result.submission.state is SubmissionState.AI_PROCESSED
    assert result.submission.review_reason is None
    assert result.submission.page_count == 3
    assert result.submission.original_filename == "student-a.pdf"
    assert len(result.submission.source_pdf_sha256) == 64

    assert len(result.answer_images) == 3
    assert all(image.status is AnswerImageStatus.OK for image in result.answer_images)

    # Every question landed on its own page, in page order -- not just "3
    # images got created somewhere".
    assert [image.page for image in result.answer_images] == [1, 2, 3]
    images_by_question = {image.question_id: image for image in result.answer_images}
    assert images_by_question.keys() == {"q-1", "q-2", "q-3"}
    assert images_by_question["q-1"].page == 1
    assert images_by_question["q-2"].page == 2
    assert images_by_question["q-3"].page == 3

    source_path = store.root / result.submission.source_pdf_path
    assert source_path.read_bytes() == data
    for image in result.answer_images:
        assert (store.root / image.image_path).exists()
    for page in (1, 2, 3):
        assert store.submission_page_image_path(result.submission.id, page).exists()

    # And the persisted rows -- not just intake_submission's in-memory
    # result -- carry the same page/question mapping back out.
    with make_uow() as uow:
        persisted = uow.answer_images.list_for_submission(result.submission.id)
    assert {(image.question_id, image.page) for image in persisted} == {
        ("q-1", 1),
        ("q-2", 2),
        ("q-3", 3),
    }


def test_missing_page_marks_submission_needs_review(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    q1 = make_question(
        id="q-1", page=1, answer_area=NormalizedRect(x=0, y=0, width=0.5, height=0.5)
    )
    q2 = make_question(id="q-2", number="問2", page=2, answer_area=None)
    _seed_test_with_questions(make_uow, questions=[q1, q2])
    data = _pdf_bytes(pages=1)  # only page 1; question 2 needs page 2

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="short.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    assert result.submission.state is SubmissionState.NEEDS_REVIEW
    assert result.submission.review_reason == "missing_pages:2"
    assert result.answer_images == ()
    # the page that *does* exist still gets a preview image for the human reviewer
    assert store.submission_page_image_path(result.submission.id, 1).exists()


def test_no_questions_registered_marks_needs_review(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    _seed_test_with_questions(make_uow, questions=[])
    data = _pdf_bytes(pages=1)

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    assert result.submission.state is SubmissionState.NEEDS_REVIEW
    assert result.submission.review_reason == "no_questions_registered"


def test_question_without_answer_area_falls_back_to_page_preview(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    q1 = make_question(id="q-1", page=1, answer_area=None)
    _seed_test_with_questions(make_uow, questions=[q1])
    data = _pdf_bytes(pages=1)

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    assert result.submission.state is SubmissionState.NEEDS_REVIEW
    assert result.submission.review_reason == "answer_area_undefined:q-1"
    assert len(result.answer_images) == 1
    image = result.answer_images[0]
    assert image.status is AnswerImageStatus.NEEDS_REVIEW
    assert image.reason == "no_answer_area_defined"
    assert image.image_path == str(
        store.submission_page_image_path(result.submission.id, 1).relative_to(store.root)
    ).replace("\\", "/")


def test_zero_area_answer_area_falls_back_to_page_preview_instead_of_a_useless_crop(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """A NormalizedRect with width or height 0 is a "defined" answer area as
    far as the domain model is concerned (it doesn't reject zero), but
    cropping it produces a meaningless 1x1px image via
    crop_normalized_rect's own clamp. This must land the same as "no answer
    area defined" -- needs_review, full page preview -- not a silent "OK".
    """
    q1 = make_question(
        id="q-1",
        page=1,
        answer_area=NormalizedRect(x=0.2, y=0.3, width=0.0, height=0.4),
    )
    _seed_test_with_questions(make_uow, questions=[q1])
    data = _pdf_bytes(pages=1)

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    assert result.submission.state is SubmissionState.NEEDS_REVIEW
    assert len(result.answer_images) == 1
    image = result.answer_images[0]
    assert image.status is AnswerImageStatus.NEEDS_REVIEW
    assert image.reason == "answer_area_zero_area"
    # Falls back to the full page preview path, not a question-crop image.
    assert image.image_path == str(
        store.submission_page_image_path(result.submission.id, 1).relative_to(store.root)
    ).replace("\\", "/")


def test_a_crop_that_came_out_blank_is_stopped_before_it_is_graded(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """Issue #122's second half, at the point it can still act.

    A detected answer area can land in the margin -- measured on real
    material, one crop came out with an ink coverage of exactly 0.0000. Sent
    on, the grading AI answered "空白なので0点" with a confidence of 0.95-1.00,
    and the screen showed a confident zero with nothing to question. Flagged
    here, `jobs.grading_processor` skips it without calling the provider and
    a person is asked to look instead.

    The same flag catches a genuinely unanswered question, and that is not a
    defect: nothing can tell the two apart from the crop, and both want a
    human.
    """
    q1 = make_question(
        id="q-1",
        page=1,
        answer_area=NormalizedRect(x=0.1, y=0.1, width=0.3, height=0.2),
    )
    _seed_test_with_questions(make_uow, questions=[q1])
    blank_sheet = PdfWriter()
    blank_sheet.add_blank_page(width=300, height=400)
    buffer = BytesIO()
    blank_sheet.write(buffer)

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=buffer.getvalue(),
            limits=_LIMITS,
            now=at(),
        )

    assert result.submission.state is SubmissionState.NEEDS_REVIEW
    assert result.submission.review_reason == "crop_nearly_blank:q-1"
    image = result.answer_images[0]
    assert image.status is AnswerImageStatus.NEEDS_REVIEW
    assert image.reason == "crop_nearly_blank"
    # The crop itself is kept, unlike the "no answer area" fallback: it is
    # exactly what would have been graded, so it is what the reviewer has to
    # be able to look at.
    assert image.image_path == str(
        store.submission_question_image_path(result.submission.id, "q-1").relative_to(store.root)
    ).replace("\\", "/")
    assert (store.root / image.image_path).exists()


def _swapped_vertical_column_questions() -> list[Question]:
    """Measured swap from ``test_answer_area_detection`` -- 問一 and 問二
    attributed to each other's columns on a vertical right-to-left sheet.

    問三 lives on page 2 so it is outside the per-page check and stays a
    control for "non-conflicted questions still grade".
    """
    return [
        make_question(
            id="q-1",
            number="問一",
            page=1,
            answer_area=NormalizedRect(x=0.639, y=0.270, width=0.064, height=0.450),
        ),
        make_question(
            id="q-2",
            number="問二",
            page=1,
            answer_area=NormalizedRect(x=0.798, y=0.270, width=0.045, height=0.401),
        ),
        make_question(
            id="q-3",
            number="問三",
            page=2,
            answer_area=NormalizedRect(x=0.100, y=0.200, width=0.080, height=0.400),
        ),
    ]


def _corrected_vertical_column_questions() -> list[Question]:
    """Same columns, labels swapped back to match reading order."""
    return [
        make_question(
            id="q-1",
            number="問一",
            page=1,
            answer_area=NormalizedRect(x=0.798, y=0.270, width=0.045, height=0.401),
        ),
        make_question(
            id="q-2",
            number="問二",
            page=1,
            answer_area=NormalizedRect(x=0.639, y=0.270, width=0.064, height=0.450),
        ),
        make_question(
            id="q-3",
            number="問三",
            page=2,
            answer_area=NormalizedRect(x=0.100, y=0.200, width=0.080, height=0.400),
        ),
    ]


def test_reading_order_conflict_stops_only_the_swapped_questions_from_grading(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """Issue #213: detection's advisory list is not consulted at confirm, so
    intake must re-derive the suspicion and refuse to trust the crops."""
    _seed_test_with_questions(make_uow, questions=_swapped_vertical_column_questions())
    data = _pdf_bytes(pages=2)

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    assert result.submission.state is SubmissionState.NEEDS_REVIEW
    by_id = {image.question_id: image for image in result.answer_images}
    assert by_id["q-1"].status is AnswerImageStatus.NEEDS_REVIEW
    assert by_id["q-1"].reason == READING_ORDER_CONFLICT_REASON
    assert by_id["q-2"].status is AnswerImageStatus.NEEDS_REVIEW
    assert by_id["q-2"].reason == READING_ORDER_CONFLICT_REASON
    assert by_id["q-3"].status is AnswerImageStatus.OK
    assert result.submission.review_reason == "reading_order_conflict:q-1,q-2"


def test_reading_order_conflict_keeps_the_crop_for_the_reviewer(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """Same contract as Issue #122's nearly-blank crop: show what would have
    been graded, but do not send it."""
    _seed_test_with_questions(
        make_uow,
        questions=_swapped_vertical_column_questions()[:2],
    )
    data = _pdf_bytes(pages=1)

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    image = result.answer_images[0]
    assert image.status is AnswerImageStatus.NEEDS_REVIEW
    assert image.reason == READING_ORDER_CONFLICT_REASON
    assert image.image_path == str(
        store.submission_question_image_path(result.submission.id, "q-1").relative_to(store.root)
    ).replace("\\", "/")
    assert (store.root / image.image_path).exists()


def test_corrected_reading_order_proceeds_to_grading(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """Once the profile is fixed, the flag must not stick around forever."""
    _seed_test_with_questions(make_uow, questions=_corrected_vertical_column_questions())
    data = _pdf_bytes(pages=2)

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    assert result.submission.state is SubmissionState.AI_PROCESSED
    assert all(image.status is AnswerImageStatus.OK for image in result.answer_images)


def test_a_blank_crop_and_an_undefined_area_are_reported_as_different_reasons(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """They send the reviewer to different places -- the registration screen
    for one, the answer for the other -- so one submission carrying both must
    not collapse them into a single label."""
    _seed_test_with_questions(
        make_uow,
        questions=[
            make_question(id="q-1", page=1, answer_area=None),
            make_question(
                id="q-2",
                number="問2",
                page=1,
                answer_area=NormalizedRect(x=0.1, y=0.1, width=0.3, height=0.2),
            ),
        ],
    )
    blank_sheet = PdfWriter()
    blank_sheet.add_blank_page(width=300, height=400)
    buffer = BytesIO()
    blank_sheet.write(buffer)

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=buffer.getvalue(),
            limits=_LIMITS,
            now=at(),
        )

    assert result.submission.review_reason == "answer_area_undefined:q-1;crop_nearly_blank:q-2"


def test_duplicate_submission_is_rejected(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    q1 = make_question(id="q-1", page=1, answer_area=NormalizedRect(x=0, y=0, width=1, height=1))
    _seed_test_with_questions(make_uow, questions=[q1])
    data = _pdf_bytes(pages=1)

    with make_uow() as uow:
        first = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    with make_uow() as uow, pytest.raises(DuplicateSubmissionError) as excinfo:
        intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a-again.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(seconds=1),
        )
    assert excinfo.value.existing_submission_id == first.submission.id

    with make_uow() as uow:
        assert len(uow.submissions.list_for_test("test-1")) == 1


def test_concurrent_duplicate_insert_is_reported_as_a_race_loss(
    make_uow: Callable[[], SqlAlchemyUnitOfWork],
    store: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two requests can both call find_by_content_hash before either commits
    and both see "nothing here yet"; only the DB's own
    uq_submissions_test_content_hash constraint (not that pre-check) actually
    stops the second insert. Simulate the race by making exactly the first
    find_by_content_hash call lie (report None even though a matching
    submission already exists), forcing intake_submission down the
    ACCEPT_NEW path until the real INSERT hits the unique constraint.
    """
    q1 = make_question(id="q-1", page=1, answer_area=NormalizedRect(x=0, y=0, width=1, height=1))
    _seed_test_with_questions(make_uow, questions=[q1])
    data = _pdf_bytes(pages=1)

    with make_uow() as uow:
        first = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    real_find = SqlAlchemySubmissionRepository.find_by_content_hash
    call_count = {"n": 0}

    def lying_once_then_real(
        self: SqlAlchemySubmissionRepository, test_id: str, source_pdf_sha256: str
    ) -> object:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return None
        return real_find(self, test_id, source_pdf_sha256)

    monkeypatch.setattr(
        SqlAlchemySubmissionRepository, "find_by_content_hash", lying_once_then_real
    )

    with make_uow() as uow, pytest.raises(DuplicateSubmissionError) as excinfo:
        intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a-race.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(seconds=5),
        )
    assert excinfo.value.existing_submission_id == first.submission.id

    with make_uow() as uow:
        assert len(uow.submissions.list_for_test("test-1")) == 1


def test_retry_reuses_the_errored_submission(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    q1 = make_question(id="q-1", page=1, answer_area=NormalizedRect(x=0, y=0, width=1, height=1))
    _seed_test_with_questions(make_uow, questions=[q1])
    data = _pdf_bytes(pages=1)

    with make_uow() as uow:
        first = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    with make_uow() as uow:
        uow.submissions.set_state(first.submission.id, SubmissionState.ERROR)
        uow.commit()

    source_path = store.root / first.submission.source_pdf_path
    mtime_before_retry = source_path.stat().st_mtime_ns

    with make_uow() as uow:
        retried = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(seconds=2),
        )

    assert retried.is_retry is True
    assert retried.submission.id == first.submission.id
    assert retried.submission.state is SubmissionState.AI_PROCESSED
    # The reintake decision table (docs/answer-intake-and-preprocessing.md §2)
    # never rewrites the source PDF on retry -- same bytes are already on disk.
    assert source_path.stat().st_mtime_ns == mtime_before_retry
    assert source_path.read_bytes() == data

    with make_uow() as uow:
        assert len(uow.submissions.list_for_test("test-1")) == 1
        assert len(uow.answer_images.list_for_submission(first.submission.id)) == 1


def test_finalization_failure_marks_error_and_a_retry_heals_the_missing_file(
    make_uow: Callable[[], SqlAlchemyUnitOfWork],
    store: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates a disk-full/permissions failure that hits partway through
    writing staged files -- after the DB transaction already committed the
    submission as ai_processed. That can't be rolled back, so the row must
    not be left stuck there: it should end up in ``error`` (with a reason
    identifying why), and re-uploading the identical PDF afterward must be
    recognized as a retry that heals the specific file that never reached
    disk, not rejected as a duplicate of a "successful" row that's actually
    missing data.
    """
    q1 = make_question(id="q-1", page=1, answer_area=NormalizedRect(x=0, y=0, width=1, height=1))
    _seed_test_with_questions(make_uow, questions=[q1])
    data = _pdf_bytes(pages=1)

    real_write_atomic = LocalFileStore.write_atomic

    def failing_write_atomic(self: LocalFileStore, path: Path, write_data: bytes) -> Path:
        if path.name == "source.pdf":
            raise OSError("simulated disk-full failure")
        return real_write_atomic(self, path, write_data)

    monkeypatch.setattr(LocalFileStore, "write_atomic", failing_write_atomic)

    with make_uow() as uow, pytest.raises(FinalizationError):
        intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    with make_uow() as uow:
        submissions = uow.submissions.list_for_test("test-1")
    assert len(submissions) == 1
    failed = submissions[0]
    assert failed.state is SubmissionState.ERROR
    assert failed.review_reason == "finalization_failed"
    source_path = store.root / failed.source_pdf_path
    assert not source_path.exists()
    # The page preview was staged (and written) before source.pdf failed.
    assert store.submission_page_image_path(failed.id, 1).exists()

    monkeypatch.setattr(LocalFileStore, "write_atomic", real_write_atomic)

    with make_uow() as uow:
        retried = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(seconds=2),
        )

    assert retried.is_retry is True
    assert retried.submission.id == failed.id
    assert retried.submission.state is SubmissionState.AI_PROCESSED
    assert source_path.read_bytes() == data


def test_repair_incomplete_submissions_moves_a_submission_with_a_missing_file_to_error(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """Standing in for a process crash or power loss between the DB commit
    and the file writes that follow it (unlike a raised write failure,
    nothing runs to flag this while it happens): a submission commits
    successfully, then one of its files is deleted out from under it
    (simulating "this write never actually completed"). The next startup's
    repair sweep must notice and move it to error, the same outcome as a
    caught FinalizationError, so a re-upload of the same PDF becomes a
    retry instead of staying rejected as a duplicate forever.
    """
    q1 = make_question(id="q-1", page=1, answer_area=NormalizedRect(x=0, y=0, width=1, height=1))
    _seed_test_with_questions(make_uow, questions=[q1])
    data = _pdf_bytes(pages=1)

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )
    assert result.submission.state is SubmissionState.AI_PROCESSED

    source_path = store.root / result.submission.source_pdf_path
    source_path.unlink()

    with make_uow() as uow:
        repaired = repair_incomplete_submissions(uow, store)
    assert repaired == [result.submission.id]

    with make_uow() as uow:
        submission = uow.submissions.get(result.submission.id)
    assert submission is not None
    assert submission.state is SubmissionState.ERROR
    assert submission.review_reason == "finalization_failed"


def test_repair_incomplete_submissions_leaves_a_fully_written_submission_alone(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    q1 = make_question(id="q-1", page=1, answer_area=NormalizedRect(x=0, y=0, width=1, height=1))
    _seed_test_with_questions(make_uow, questions=[q1])

    with make_uow() as uow:
        result = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=_pdf_bytes(pages=1),
            limits=_LIMITS,
            now=at(),
        )

    with make_uow() as uow:
        repaired = repair_incomplete_submissions(uow, store)
    assert repaired == []

    with make_uow() as uow:
        submission = uow.submissions.get(result.submission.id)
    assert submission is not None
    assert submission.state is SubmissionState.AI_PROCESSED


def test_reintake_of_an_errored_submission_with_downstream_processing_is_rejected(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """An errored submission that already has downstream data attached (here,
    a queued job -- standing in for a later OCR/AI grading issue) must not be
    silently retried in place: in-place retry only replaces answer_images, so
    that would leave the job (and any recognition/grade/review rows) orphaned
    against a freshly regenerated set of images. Re-uploading the identical
    PDF is reported the same as any other non-retryable duplicate instead.
    """
    q1 = make_question(id="q-1", page=1, answer_area=NormalizedRect(x=0, y=0, width=1, height=1))
    _seed_test_with_questions(make_uow, questions=[q1])
    data = _pdf_bytes(pages=1)

    with make_uow() as uow:
        first = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    with make_uow() as uow:
        uow.jobs.add(make_job(submission_id=first.submission.id))
        uow.submissions.set_state(first.submission.id, SubmissionState.ERROR)
        uow.commit()

    with make_uow() as uow, pytest.raises(DuplicateSubmissionError) as excinfo:
        intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a-again.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(seconds=2),
        )
    assert excinfo.value.existing_submission_id == first.submission.id

    with make_uow() as uow:
        submission = uow.submissions.get(first.submission.id)
    assert submission is not None
    assert submission.state is SubmissionState.ERROR  # untouched by the rejected retry


def test_concurrent_retry_is_reported_as_a_race_loss(
    make_uow: Callable[[], SqlAlchemyUnitOfWork],
    store: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two requests can both decide RETRY_EXISTING for the same errored
    submission before either claims it; only claim_for_retry()'s conditional
    UPDATE (WHERE state = 'error') actually arbitrates. Simulate the loser by
    making claim_for_retry report False even though nothing else changed the
    row, and confirm intake_submission surfaces that as
    SubmissionRetryConflictError instead of silently re-running the pipeline.
    """
    q1 = make_question(id="q-1", page=1, answer_area=NormalizedRect(x=0, y=0, width=1, height=1))
    _seed_test_with_questions(make_uow, questions=[q1])
    data = _pdf_bytes(pages=1)

    with make_uow() as uow:
        first = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(),
        )

    with make_uow() as uow:
        uow.submissions.set_state(first.submission.id, SubmissionState.ERROR)
        uow.commit()

    monkeypatch.setattr(
        SqlAlchemySubmissionRepository, "claim_for_retry", lambda self, submission_id: False
    )

    with make_uow() as uow, pytest.raises(SubmissionRetryConflictError) as excinfo:
        intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=data,
            limits=_LIMITS,
            now=at(seconds=2),
        )
    assert excinfo.value.submission_id == first.submission.id

    with make_uow() as uow:
        # The loser's staged files/state changes were rolled back -- the
        # submission is exactly where the "winner" (simulated by never
        # actually running) left it: still ERROR, still one answer image.
        submission = uow.submissions.get(first.submission.id)
        assert submission is not None
        assert submission.state is SubmissionState.ERROR
        assert len(uow.answer_images.list_for_submission(first.submission.id)) == 1


def test_unknown_test_id_raises_lookup_error(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    with make_uow() as uow, pytest.raises(LookupError):
        intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="does-not-exist",
            filename="a.pdf",
            declared_mime=None,
            data=_pdf_bytes(),
            limits=_LIMITS,
            now=at(),
        )


def test_encrypted_pdf_is_rejected_without_a_trace(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    _seed_test_with_questions(make_uow, questions=[])

    with make_uow() as uow, pytest.raises(PdfEncryptedError):
        intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=_encrypted_pdf_bytes(),
            limits=_LIMITS,
            now=at(),
        )

    with make_uow() as uow:
        assert uow.submissions.list_for_test("test-1") == []
    # nothing was ever written to app-data/submissions/ for the rejected upload
    assert not (store.root / "submissions").exists()


def test_oversize_page_count_is_rejected(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    _seed_test_with_questions(make_uow, questions=[])
    tiny_limits = IntakeLimits(max_size_bytes=10 * 1024 * 1024, max_pages=2)

    with make_uow() as uow, pytest.raises(PdfPageLimitExceededError):
        intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=_pdf_bytes(pages=3),
            limits=tiny_limits,
            now=at(),
        )

    with make_uow() as uow:
        assert uow.submissions.list_for_test("test-1") == []


def test_page_with_an_absurd_declared_size_is_rejected_before_rendering(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """A tiny PDF can still declare an enormous MediaBox; this must be caught
    before render_page_png ever tries to allocate a raster from it.
    """
    _seed_test_with_questions(make_uow, questions=[])
    huge_page = _pdf_bytes(width=1_000_000, height=1_000_000)
    assert len(huge_page) < 10_000  # a tiny file, not caught by the size limit

    with make_uow() as uow, pytest.raises(PdfPageTooLargeError):
        intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=huge_page,
            limits=_LIMITS,
            now=at(),
        )

    with make_uow() as uow:
        assert uow.submissions.list_for_test("test-1") == []
    assert not (store.root / "submissions").exists()


def test_decoded_output_exceeding_the_staged_size_cap_is_rejected(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """A page's declared size and its compressed bytes on disk can both look
    fine while the *decoded* raster is huge -- the per-page checks above
    don't catch that. A tiny max_staged_output_bytes cap stands in for that
    case here: even one rendered+preprocessed page trips it, proving the
    limit is actually enforced (not just present on IntakeLimits), and that
    tripping it leaves no DB row or file behind, same as any other rejection.
    """
    _seed_test_with_questions(make_uow, questions=[])
    tiny_staged_limits = IntakeLimits(
        max_size_bytes=10 * 1024 * 1024, max_pages=20, max_staged_output_bytes=100
    )

    with make_uow() as uow, pytest.raises(StagedOutputTooLargeError):
        intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=_pdf_bytes(pages=1),
            limits=tiny_staged_limits,
            now=at(),
        )

    with make_uow() as uow:
        assert uow.submissions.list_for_test("test-1") == []
    assert not (store.root / "submissions").exists()


class _RenderFailingPdfEngine:
    """Delegates to a real ``PdfEngine`` but fails to render one specific
    page -- standing in for a PDF whose page tree/geometry pypdf considers
    entirely valid (so every earlier check passes) but whose content stream
    only the renderer itself rejects.
    """

    def __init__(self, delegate: PdfEngine, *, fails_on_page_index: int) -> None:
        self._delegate = delegate
        self._fails_on_page_index = fails_on_page_index

    def page_count(self, source: Path) -> int:
        return self._delegate.page_count(source)

    def is_encrypted(self, source: Path) -> bool:
        return self._delegate.is_encrypted(source)

    def page_geometry(self, source: Path, page_index: int) -> PageGeometry:
        return self._delegate.page_geometry(source, page_index)

    def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
        if page_index == self._fails_on_page_index:
            raise RuntimeError("simulated PDFium render failure")
        return self._delegate.render_page_png(source, page_index, scale=scale)

    def stamp_markers(
        self,
        source: Path,
        destination: Path,
        markers: Mapping[int, Sequence[NormalizedPoint]],
        *,
        mark_size_pt: float = 8.0,
    ) -> None:
        self._delegate.stamp_markers(source, destination, markers, mark_size_pt=mark_size_pt)

    def render_annotations(
        self,
        source: Path,
        destination: Path,
        marks: Mapping[int, Sequence[AnnotationMark]],
        note_pages: Sequence[Sequence[AnnotationMark]] = (),
    ) -> None:
        self._delegate.render_annotations(source, destination, marks, note_pages)


def test_a_render_failure_is_reported_as_pdf_corrupted_not_an_unhandled_error(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """A page can pass every check done from its page tree/geometry (which is
    all pypdf ever looks at) and still fail only when PDFium actually tries
    to render it -- an unsupported/malformed content stream, say. That must
    surface as the documented bad-PDF rejection (PdfCorruptedError, mapped to
    400), not an unhandled exception (500), and must leave no DB row or file
    behind, same as any other rejection caught before this point.
    """
    _seed_test_with_questions(make_uow, questions=[])
    failing_engine = _RenderFailingPdfEngine(_ENGINE, fails_on_page_index=0)

    with make_uow() as uow, pytest.raises(PdfCorruptedError):
        intake_submission(
            uow,
            store,
            failing_engine,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.pdf",
            declared_mime=None,
            data=_pdf_bytes(pages=1),
            limits=_LIMITS,
            now=at(),
        )

    with make_uow() as uow:
        assert uow.submissions.list_for_test("test-1") == []
    assert not (store.root / "submissions").exists()


def test_wrong_extension_is_rejected_before_any_pdf_parsing(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    _seed_test_with_questions(make_uow, questions=[])

    with make_uow() as uow, pytest.raises(PdfInvalidTypeError):
        intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="a.txt",
            declared_mime=None,
            data=_pdf_bytes(),
            limits=_LIMITS,
            now=at(),
        )


def test_two_page_question_intake_success_and_extra_pages_safety_gate(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
    """Issue #108 / Issue #215 integration:
    1. A test with a 2-page question spanning pages 2 and 3 has expected_pages={1, 2, 3}.
       A 3-page submission has full coverage: state is AI_PROCESSED, the 2-page question
       crop is combined vertically, and answer images are sorted by question order.
    2. A 4-page submission to the same test triggers Issue #215's safety gate:
       state is NEEDS_REVIEW with review_reason 'extra_pages:4>3'.
    """
    q1 = make_question(
        id="q-1",
        number="問1",
        page=1,
        answer_area=NormalizedRect(x=0.1, y=0.1, width=0.8, height=0.3),
    )
    q2 = make_question(
        id="q-2",
        number="問2",
        page=2,
        answer_area=NormalizedRect(x=0.1, y=0.1, width=0.8, height=0.3),
    )
    q3 = make_question(
        id="q-3",
        number="問3",
        page=2,
        page_2=3,
        answer_area=NormalizedRect(x=0.1, y=0.5, width=0.8, height=0.4),
        answer_area_2=NormalizedRect(x=0.1, y=0.1, width=0.8, height=0.4),
    )
    _seed_test_with_questions(make_uow, questions=[q1, q2, q3])

    # 1. 3-page submission -> full coverage, Q3 crop combined
    data_3p = _pdf_bytes(pages=3)
    with make_uow() as uow:
        result_3p = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="student-3p.pdf",
            declared_mime="application/pdf",
            data=data_3p,
            student_label="student-3p",
            limits=_LIMITS,
            now=at(),
        )

    assert result_3p.submission.state is SubmissionState.AI_PROCESSED
    assert result_3p.submission.review_reason is None
    assert result_3p.submission.page_count == 3
    assert len(result_3p.answer_images) == 3
    assert [img.question_id for img in result_3p.answer_images] == ["q-1", "q-2", "q-3"]
    assert all(img.status is AnswerImageStatus.OK for img in result_3p.answer_images)

    q3_img = next(img for img in result_3p.answer_images if img.question_id == "q-3")
    assert q3_img.page == 2
    q3_file = store.root / q3_img.image_path
    assert q3_file.is_file()
    assert q3_file.stat().st_size > 0

    # 2. 4-page submission -> genuine coverage mismatch halts at NEEDS_REVIEW
    data_4p = _pdf_bytes(pages=4)
    with make_uow() as uow:
        result_4p = intake_submission(
            uow,
            store,
            _ENGINE,
            _PREPROCESSOR,
            test_id="test-1",
            filename="student-4p.pdf",
            declared_mime="application/pdf",
            data=data_4p,
            student_label="student-4p",
            limits=_LIMITS,
            now=at(),
        )

    assert result_4p.submission.state is SubmissionState.NEEDS_REVIEW
    assert result_4p.submission.review_reason == "extra_pages:4>3"
    assert len(result_4p.answer_images) == 0
