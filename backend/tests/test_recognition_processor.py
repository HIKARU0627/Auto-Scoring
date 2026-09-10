"""Tests for `auto_scoring.jobs.recognition_processor.RecognitionJobProcessor`
(Issue #19), against a real on-disk SQLite database and `LocalFileStore`, with
a scriptable fake `OCRProvider` -- no real OCR service is called. The shipped
adapter for the service decision A names (Google Document AI,
business-rules-and-evaluation-data.md section 3 (A)) has its own tests in
``test_document_ai_provider.py``; this file is about what the processor does
with whatever a provider returns or raises.
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
    OCRUnavailable,
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


async def test_one_unreadable_span_records_where_it_is_without_stopping_the_question(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    """Issue #158. This reading used to come back ``usable=False``, because
    the gate was the worst span's confidence and one span was unreadable.

    What the reader gets instead is *which* span: the persisted boxes say
    which part of the answer the reading is missing, and the row keeps the
    worst span's confidence as a number to show. The question is not stopped
    for it -- a longer answer contains more spans, so "one of them was
    unreadable" is a fact about length, not about whether this answer was
    read (docs/ocr-recognition-pipeline.md §9).
    """
    _seed(session_factory, store)
    provider.script(
        OcrResult(
            text="?光",
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
    assert result.usable is True
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        history = uow.recognitions.history("sub-1", "q-1")
    # Display only, and no longer compared against anything.
    assert history[0].confidence == pytest.approx(0.12)
    boxes = history[0].boxes
    assert [box.unreadable for box in boxes] == [True, False]
    assert boxes[0].rect.x == pytest.approx(0.1)  # where to look on the crop


@pytest.mark.parametrize("spans", [1, 2, 3, 8, 20])
async def test_the_same_handwriting_stays_usable_however_much_was_written(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
    spans: int,
) -> None:
    """The property, at the boundary that actually decides a question.

    Every span is drawn from one fixed mixture of qualities, so a longer
    reading here is a longer answer in the same hand. Under the old rule the
    minimum fell with each extra draw and the question flipped to unusable at
    the third span; nothing about the reading's *quality* changed at that
    point. A single example cannot hold this down -- it is the shape of the
    curve, not one point on it, that Issue #158 is about.
    """
    qualities = (
        (0.97, ConfidenceBand.HIGH),
        (0.85, ConfidenceBand.MEDIUM),
        (0.62, ConfidenceBand.LOW),
    )
    _seed(session_factory, store)
    provider.script(
        OcrResult(
            text="x" * spans,
            tokens=tuple(
                # Laid out left to right; `_token`'s own width is 0.2, so the
                # last box has to start well inside the page.
                _token("x", *qualities[index % len(qualities)], x=index * (0.7 / spans))
                for index in range(spans)
            ),
            provider=provider.name,
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.usable is True


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


async def test_a_host_with_no_ocr_records_no_reading_and_does_not_block(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    """Issue #114. "This machine has no OCR" is a third case, distinct from
    both "read it and was unsure" (low confidence, still persisted, still
    blocks) and "the call failed" (FAILED, retried).

    Two things are asserted because both were wrong before:

    * **No `RecognitionResult` is written.** The deleted ``NullOCRProvider``
      wrote one at ``confidence=0.0``, which design section 8.1.4 forbids
      ("読めていないものに数値を与えない") and which is indistinguishable in
      review from an OCR that looked and found nothing.
    * **``usable`` is True**, meaning "no OCR term to gate on". It was False,
      which made every question on such a host `BLOCKED` for its dependents
      until a human pressed /resume on each one -- while design section 24
      says "OCR失敗: **採点は止めない。**"
    """
    _seed(session_factory, store)
    provider.script(OCRUnavailable("no OCR provider is configured: X is not set"))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is True
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.recognitions.history("sub-1", "q-1") == []


async def test_an_unreadable_reading_still_blocks_even_though_no_ocr_does_not(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    """The pair that makes the distinction real (Issue #114 acceptance 8).

    An OCR that read the crop and got nothing out of it is the case
    business-rules-and-evaluation-data.md section 4.4 was written for, and
    Issue #114 deliberately left it alone: the row exists, the confidence is
    real, and the dependent question waits for a human. Only the *absence of
    a provider* stops gating.
    """
    _seed(session_factory, store)
    provider.script(
        OcrResult(
            text="",
            tokens=(_token("", 0.0, ConfidenceBand.LOW),),
            provider="scripted",
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is False
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        # The row is what tells the two cases apart afterwards.
        assert len(uow.recognitions.history("sub-1", "q-1")) == 1


async def test_a_reading_with_no_tokens_at_all_is_not_usable(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    """The provider answered and returned nothing to read.

    docs/ocr-recognition-pipeline.md §8.5 left this case stopping the
    question deliberately -- it is "the OCR genuinely could not read this",
    not "this host has no OCR" -- and Issue #158 did not loosen it: with no
    tokens there is no readable span.
    """
    _seed(session_factory, store)
    provider.script(OcrResult(text="", tokens=(), provider=provider.name))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is False
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert len(uow.recognitions.history("sub-1", "q-1")) == 1


async def test_reprocessing_a_reading_with_nothing_readable_still_does_not_release_it(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    """The crash-recovery path reads the verdict back off the persisted
    spans, so those spans have to carry which ones were unreadable.

    Without that, a reading nothing could be got out of would stop the
    question when it was recognized and release it when the job was retried
    after a crash -- the same reading, two answers.
    """
    _seed(session_factory, store)
    provider.script(
        OcrResult(
            text="??",
            tokens=(
                _token("?", 0.12, ConfidenceBand.LOW),
                _token("?", 0.20, ConfidenceBand.LOW, x=0.4),
            ),
            provider=provider.name,
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    first = await processor.process(job)
    second = await processor.process(job)

    assert first.usable is False
    assert second.usable is False
    assert provider.calls == [_IMAGE_BYTES]


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


async def test_rate_limited_retry_after_reaches_the_processing_result(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    """Issue #153: a 429's parsed ``Retry-After`` (already resolved to
    seconds by the adapter -- `OCRRateLimitedError.retry_after_seconds`) must
    survive the trip through `RecognitionJobProcessor._failed` into
    `ProcessingResult`, so `auto_scoring.jobs.queue.JobQueueService` can
    honour it instead of guessing a delay."""
    _seed(session_factory, store)
    provider.script(OCRRateLimitedError("boom", retry_after_seconds=30.0))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.error_category is ErrorCategory.RATE_LIMITED
    assert result.retry_after_seconds == 30.0


async def test_timeout_never_carries_a_retry_after(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    """A TIMEOUT/SERVER_ERROR failure has no `Retry-After` concept -- must
    not carry one through even if some future adapter mistakenly set it."""
    _seed(session_factory, store)
    provider.script(OCRTimeoutError("boom"))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.error_category is ErrorCategory.TIMEOUT
    assert result.retry_after_seconds is None
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.recognitions.history("sub-1", "q-1") == []


async def test_reprocessing_recomputes_usable_from_the_persisted_spans(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    """The crash-recovery path must answer the same question the fresh path
    does (Issue #158).

    The row here carries a low `RecognitionResult.confidence` -- the worst
    span's -- but records a readable span next to the unreadable one. Reading
    the outcome back off that number, as this path used to, would make the
    same reading usable when it was recognized and unusable when the job was
    retried after a crash.
    """
    _seed(session_factory, store)
    provider.script(
        OcrResult(
            text="?光",
            tokens=(
                _token("?", 0.12, ConfidenceBand.LOW),
                _token("光", 0.9, ConfidenceBand.HIGH, x=0.4),
            ),
            provider=provider.name,
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    first = await processor.process(job)
    second = await processor.process(job)

    assert first.usable is True
    assert second.usable is True
    assert provider.calls == [_IMAGE_BYTES]


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

    # The reading's only span scores below the configured threshold, so
    # nothing in it was readable. The threshold still comes from the single
    # configured place (business rules §3.1 (C)); Issue #158 changed what it
    # is compared against -- each span, not one aggregate for the answer.
    assert result.usable is False


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


async def test_reprocessing_the_same_job_after_a_crash_does_not_call_the_provider_twice(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    provider: _ScriptedOCRProvider,
    processor: RecognitionJobProcessor,
) -> None:
    """Simulates jobs.queue's crash-recovery path: the same Job row (same
    `job.id`) is handed to `process` again after an earlier call already
    committed a RecognitionResult but the queue never got to record the
    job's own SUCCEEDED transition (Issue #19 review round 1, P1). The
    second call must recompute the outcome from the already-persisted
    result instead of calling the provider again and adding a duplicate.
    """
    _seed(session_factory, store)
    provider.script(
        OcrResult(
            text="光合成", tokens=(_token("光合成", 0.96, ConfidenceBand.HIGH),), provider="x"
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    first = await processor.process(job)
    second = await processor.process(job)

    assert first.usable is True
    assert second.outcome is ProcessingOutcome.SUCCEEDED
    assert second.usable is True
    assert provider.calls == [_IMAGE_BYTES]  # only the first call reached the provider
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        history = uow.recognitions.history("sub-1", "q-1")
    assert len(history) == 1
