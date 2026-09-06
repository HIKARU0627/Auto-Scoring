"""Tests for `auto_scoring.jobs.recognition_processor.RecognitionJobProcessor`
(Issue #19), against a real on-disk SQLite database and `LocalFileStore`, with
a scriptable fake `OCRProvider` -- no real OCR service is called (decision A,
business-rules-and-evaluation-data.md section 3 (A), is still pending).
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.job_execution import ProcessingOutcome
from auto_scoring.domain.models import AnswerImageStatus, ErrorCategory, JobKind
from auto_scoring.domain.ocr import (
    BoundingBox,
    ConfidenceBand,
    OCRRateLimitedError,
    OCRResponseSchemaError,
    OcrResult,
    OCRServerError,
    OCRTimeoutError,
    OcrToken,
)
from auto_scoring.jobs.recognition_processor import RecognitionJobProcessor
from auto_scoring.jobs.recognition_settings import RecognitionSettings
from tests.support import make_answer_image, make_job, make_question, make_submission, make_test

_IMAGE_BYTES = b"\x89PNG\r\n\x1a\n-fake-question-crop-"


class _ScriptedOCRProvider:
    """Returns/raises whatever ``script`` was told to, once per call."""

    name = "scripted"

    def __init__(self) -> None:
        self.calls: list[bytes] = []
        self._next: OcrResult | Exception | None = None

    def script(self, outcome: OcrResult | Exception) -> None:
        self._next = outcome

    def recognize(self, image: bytes, *, language: str = "ja") -> OcrResult:
        self.calls.append(image)
        assert self._next is not None, "no outcome scripted"
        if isinstance(self._next, Exception):
            raise self._next
        return self._next


def _token(text: str, confidence: float, band: ConfidenceBand, *, x: float = 0.1) -> OcrToken:
    return OcrToken(
        text=text, bounding_box=BoundingBox(x, 0.2, 0.2, 0.05), confidence=confidence, band=band
    )


@pytest.fixture
def provider() -> _ScriptedOCRProvider:
    return _ScriptedOCRProvider()


@pytest.fixture
def processor(
    session_factory: sessionmaker[Session], store: LocalFileStore, provider: _ScriptedOCRProvider
) -> RecognitionJobProcessor:
    return RecognitionJobProcessor(session_factory, store, provider)


def _seed(
    session_factory: sessionmaker[Session], store: LocalFileStore, **overrides: object
) -> None:
    image = make_answer_image(**overrides)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question())
        uow.submissions.add(make_submission())
        uow.answer_images.add(image)
        uow.commit()
    if image.status is AnswerImageStatus.OK:
        store.write_atomic(store.root / image.image_path, _IMAGE_BYTES)


async def test_high_confidence_result_is_usable_and_persisted(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    _seed(session_factory, store)
    provider.script(
        OcrResult(
            text="光合成",
            tokens=(_token("光合成", 0.96, ConfidenceBand.HIGH),),
            provider=provider.name,
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is True
    assert provider.calls == [_IMAGE_BYTES]
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        history = uow.recognitions.history("sub-1", "q-1")
    assert len(history) == 1
    assert history[0].text == "光合成"
    assert history[0].confidence == pytest.approx(0.96)
    assert history[0].boxes[0].text == "光合成"
    assert history[0].boxes[0].rect.x == pytest.approx(0.1)


async def test_low_confidence_result_is_not_usable_but_still_persisted(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    _seed(session_factory, store)
    provider.script(
        OcrResult(
            text="?",
            tokens=(
                _token("?", 0.12, ConfidenceBand.LOW),
                _token("光", 0.9, ConfidenceBand.HIGH, x=0.4),
            ),
            provider=provider.name,
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is False  # worst-token confidence gates the whole question
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        history = uow.recognitions.history("sub-1", "q-1")
    assert history[0].confidence == pytest.approx(0.12)


async def test_needs_review_answer_image_skips_the_provider(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    _seed(
        session_factory,
        store,
        status=AnswerImageStatus.NEEDS_REVIEW,
        reason="page_count_mismatch",
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is False
    assert provider.calls == []  # never spent an external call on an untrusted crop
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.recognitions.history("sub-1", "q-1") == []


async def test_missing_question_id_fails_permanently_without_calling_the_provider(
    provider: _ScriptedOCRProvider, processor: RecognitionJobProcessor
) -> None:
    job = make_job(kind=JobKind.GRADING, question_id=None)

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is ErrorCategory.PERMANENT
    assert provider.calls == []


async def test_missing_answer_image_fails_permanently(
    session_factory: sessionmaker[Session], processor: RecognitionJobProcessor
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question())
        uow.submissions.add(make_submission())
        uow.commit()
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is ErrorCategory.PERMANENT


@pytest.mark.parametrize(
    ("raised", "expected_category"),
    [
        (OCRTimeoutError("boom"), ErrorCategory.TIMEOUT),
        (OCRRateLimitedError("boom"), ErrorCategory.RATE_LIMITED),
        (OCRServerError("boom"), ErrorCategory.SERVER_ERROR),
        (OCRResponseSchemaError("boom"), ErrorCategory.PERMANENT),
    ],
)
async def test_provider_errors_are_classified_and_never_leak_the_raw_message(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
    raised: Exception,
    expected_category: ErrorCategory,
) -> None:
    _seed(session_factory, store)
    provider.script(raised)
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is expected_category
    assert result.error_message is not None
    assert "boom" not in result.error_message
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.recognitions.history("sub-1", "q-1") == []


async def test_confidence_threshold_is_configurable(
    session_factory: sessionmaker[Session], store: LocalFileStore, provider: _ScriptedOCRProvider
) -> None:
    _seed(session_factory, store)
    strict_processor = RecognitionJobProcessor(
        session_factory, store, provider, settings=RecognitionSettings(confidence_threshold=0.99)
    )
    provider.script(
        OcrResult(text="光", tokens=(_token("光", 0.96, ConfidenceBand.HIGH),), provider="x")
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await strict_processor.process(job)

    assert result.usable is False  # 0.96 < the configured 0.99 threshold


async def test_bounding_box_at_the_page_edge_is_clamped_not_rejected(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    """`domain.ocr.BoundingBox` tolerates a tiny epsilon past 1.0;
    `domain.models.NormalizedRect` does not. A provider result sitting right
    at that boundary must still persist, not blow up the whole job."""
    _seed(session_factory, store)
    edge_box = BoundingBox(x=0.9999999995, y=0.0, width=0.0000000009, height=0.1)
    edge_token = OcrToken(text="x", bounding_box=edge_box, confidence=0.9, band=ConfidenceBand.HIGH)
    provider.script(OcrResult(text="x", tokens=(edge_token,), provider="x"))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        boxes = uow.recognitions.history("sub-1", "q-1")[0].boxes
    assert boxes[0].rect.x + boxes[0].rect.width <= 1.0
