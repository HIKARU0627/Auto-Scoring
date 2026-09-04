"""Integration tests for adapters.submission_intake.intake_submission.

Exercises the full pipeline against a real on-disk SQLite DB and a real
``LocalFileStore``, with the real ``PdfiumPypdfEngine`` / ``OpenCvImagePreprocessor``
adapters -- this is the "複数page/回転/破損/oversize/重複PDFを含む
integration test" Issue #17 asks for.
"""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO

import pytest
from pypdf import PdfWriter

from auto_scoring.adapters.image.opencv_preprocessor import OpenCvImagePreprocessor
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf import PdfiumPypdfEngine
from auto_scoring.adapters.submission_intake import (
    DuplicateSubmissionError,
    intake_submission,
)
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import (
    AnswerImageStatus,
    NormalizedRect,
    Question,
    SubmissionState,
)
from auto_scoring.domain.pdf_intake import (
    IntakeLimits,
    PdfEncryptedError,
    PdfInvalidTypeError,
    PdfPageLimitExceededError,
)
from tests.support import at, make_question, make_test

_ENGINE = PdfiumPypdfEngine()
_PREPROCESSOR = OpenCvImagePreprocessor()
_LIMITS = IntakeLimits(max_size_bytes=10 * 1024 * 1024, max_pages=20)


def _pdf_bytes(*, pages: int = 1, width: float = 300, height: float = 400) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=height)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


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
        uow.tests.add(make_test(id=test_id))
        for question in questions or []:
            uow.questions.add(question)
        uow.commit()


def test_happy_path_creates_submission_and_ok_answer_images(
    make_uow: Callable[[], SqlAlchemyUnitOfWork], store: LocalFileStore
) -> None:
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
    _seed_test_with_questions(make_uow, questions=[q1, q2])
    data = _pdf_bytes(pages=2)

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
    assert result.submission.page_count == 2
    assert result.submission.original_filename == "student-a.pdf"
    assert len(result.submission.source_pdf_sha256) == 64

    assert len(result.answer_images) == 2
    assert all(image.status is AnswerImageStatus.OK for image in result.answer_images)

    source_path = store.root / result.submission.source_pdf_path
    assert source_path.read_bytes() == data
    for image in result.answer_images:
        assert (store.root / image.image_path).exists()
    for page in (1, 2):
        assert store.submission_page_image_path(result.submission.id, page).exists()


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
