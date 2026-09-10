"""`JobProcessor` for the recognition step of Issue #18's per-question job
(docs/job-queue.md: "1 Question = 1 Job(JobKind.GRADING)... 個々のJobの内部で
OCR→採点をどう分けるかはJobProcessor実装側の自由").

This is only the OCR half. Grading (`AIProvider`) and Annotation generation
are a later issue's responsibility ("対象外", GitHub Issue #19); until that
exists, a job this processor completes reports its outcome purely from the
recognition step so the DAG (`domain.job_scheduling`) already has something
usable to gate on -- a dependent question relies on its prerequisite's
*recognized text*, not a grade (business-rules-and-evaluation-data.md
section 4.3: "依存元設問の確定した... OCR テキスト").

Framework-adjacent, not domain: this is the concrete boundary the `domain.
ocr.OCRProvider` and `domain.job_execution.JobProcessor` ports plug into
(`adapters.unit_of_work.SqlAlchemyUnitOfWork`, `adapters.local_storage.
LocalFileStore`), mirroring `auto_scoring.jobs.queue`'s own place in the
architecture.
"""

from __future__ import annotations

from asyncio import to_thread
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import (
    AnswerImageStatus,
    ErrorCategory,
    GradingSource,
    Job,
    NormalizedRect,
    RecognitionResult,
    find_answer_image,
)
from auto_scoring.domain.models import (
    BoundingBox as ModelsBoundingBox,
)
from auto_scoring.domain.ocr import (
    OCRProvider,
    OCRProviderError,
    OCRRateLimitedError,
    OCRResponseSchemaError,
    OCRServerError,
    OCRTimeoutError,
    OcrToken,
    OCRUnavailable,
    UnreadableSpans,
    lowest_token_confidence,
    unreadable_spans,
)
from auto_scoring.jobs.clock import Clock, SystemClock
from auto_scoring.jobs.recognition_settings import RecognitionSettings

#: Recognized text is always requested in Japanese for the MVP (business-
#: rules-and-evaluation-data.md is scoped to Japanese handwriting throughout;
#: `OCRProvider.recognize`'s ``language`` parameter exists for a later,
#: non-Japanese test format).
_LANGUAGE = "ja"


def _clamp_unit(value: float) -> float:
    return min(1.0, max(0.0, value))


def _to_domain_boxes(
    tokens: tuple[OcrToken, ...], unreadable: UnreadableSpans
) -> tuple[ModelsBoundingBox, ...]:
    """Translate the provider's normalized boxes into the persisted domain
    type, carrying which spans could not be read.

    Clamped defensively: `domain.ocr.BoundingBox` tolerates a tiny
    floating-point overshoot past 1.0 (its own epsilon), but
    `domain.models.NormalizedRect` does not -- a real provider's raw
    normalized coordinates should never need this, but persisting a
    `RecognitionResult` must not fail outright over a rounding error at the
    page edge.

    The unreadable spans ride along on the boxes because the box *is* the
    position (Issue #158): a reviewer needs to see which part of the answer
    the reading is missing, and a count on the row could not say that.
    """
    unreadable_indices = set(unreadable.indices)
    boxes = []
    for index, token in enumerate(tokens):
        box = token.bounding_box
        x = _clamp_unit(box.x)
        y = _clamp_unit(box.y)
        width = _clamp_unit(min(box.width, 1.0 - x))
        height = _clamp_unit(min(box.height, 1.0 - y))
        boxes.append(
            ModelsBoundingBox(
                text=token.text,
                rect=NormalizedRect(x=x, y=y, width=width, height=height),
                unreadable=index in unreadable_indices,
            )
        )
    return tuple(boxes)


def _nothing_readable(boxes: tuple[ModelsBoundingBox, ...]) -> bool:
    """The persisted form of `domain.ocr.UnreadableSpans.nothing_readable`.

    Used only on the crash-recovery path, where the reading is already a row
    and the provider must not be called again. Rows written before Issue #158
    carry no per-span flag, so they read back as fully readable -- which is
    the same answer the new rule gives for a reading that had any readable
    span at all, and the case it changed (`domain.models.BoundingBox`).
    """
    return all(box.unreadable for box in boxes)


def recognition_result_id(job: Job) -> str:
    """Deterministic id for the `RecognitionResult` a successful recognition
    of ``job`` produces.

    `JobState.SUCCEEDED` is a dead end (`domain.models._JOB_TRANSITIONS`) --
    a job is only ever RUNNING more than once if an earlier attempt crashed
    or errored, so a row already existing under this id can only mean an
    earlier attempt of this *exact* job (same `job.id`; a reissued job for a
    new dependency-graph version gets a new id, see
    `reissue_job_for_graph_version`) already recognized and persisted it but
    the process died, or `jobs.queue._finalize_result` hit a DB error,
    before the queue recorded the SUCCEEDED transition (Issue #19 review
    round 1, P1). `process` uses this to recompute the outcome from the
    existing row instead of calling the provider again and persisting a
    duplicate AI proposal.

    Public (not a leading-underscore name) so
    `auto_scoring.jobs.grading_processor.GradingJobProcessor` -- which
    composes this processor for the recognition half of a job and then reads
    the row it persisted to feed the grading half -- computes the exact same
    id rather than duplicating the format string (Issue #20).
    """
    return f"recognition:{job.id}"


class RecognitionJobProcessor:
    """Recognizes one question's answer image via `OCRProvider` and persists
    the result as a `RecognitionResult` (source=AI, always -- Issue #19
    acceptance: never auto-confirm).

    ``usable`` on a `ProcessingResult.SUCCEEDED` outcome is **"at least one
    span of this crop came back readable"** -- `domain.ocr.unreadable_spans`,
    which scores each token against `settings.confidence_threshold` and
    reports which ones fell below it. A reading with nothing readable at all
    routes the question to needs_review (any dependent stays `BLOCKED`,
    business-rules-and-evaluation-data.md section 4.4) without ever raising
    -- an unreadable read is a completed recognition, not a processing
    failure (`domain.ocr.OcrToken`'s own docstring: an unreadable span is
    still returned, never dropped).

    **It used to be ``overall_confidence(...) >= threshold``, and that
    measured the length of the answer** (Issue #158). That aggregate is the
    minimum over every token, so each additional span is another chance to
    pull it under the threshold: on the 15 recorded readings of 2026-09-09
    every reading of 5 tokens or fewer passed and every one of 9 tokens or
    more failed, while correctness did not separate them at all. Whatever
    else a gate is, it must not stop a question for being long -- see
    docs/ocr-recognition-pipeline.md §9 for the numbers and for why no new
    threshold replaced it. The unreadable spans are persisted per box
    instead, as information for the reviewer.

    **A host with no OCR at all is a third case, not a low-confidence read**
    (Issue #114). `domain.ocr.OCRUnavailable` yields ``SUCCEEDED`` with no
    `RecognitionResult` persisted and ``usable=True``, which for this half
    means "there is no OCR term to gate on" rather than "the reading was
    good": design section 24 requires grading to carry on without a reading,
    and section 8.1.4 forbids inventing a confidence number for one. The
    two cases stay distinguishable afterwards by whether a
    `RecognitionResult` row exists at all -- which is the point (Issue #114
    acceptance 8: "本当に読めなかった" and "読む道具が無い" are different
    facts).

    That ``usable=True`` is only sound because this processor is always
    composed into `jobs.grading_processor.GradingJobProcessor`, which ANDs
    it with the grading half; it is never the queue's processor on its own
    (`api.app.create_app`). Running it standalone on a host with no OCR
    would release a dependent question against nothing at all.

    ``ProcessingOutcome.FAILED`` is reserved for the provider not producing a
    result at all (`domain.ocr.OCRProviderError` and its subclasses):
    timeout, rate limit, and a malformed/unparseable response are classified
    into `ErrorCategory` here so the queue's existing retry policy
    (`domain.retry_policy`) applies unchanged; any other exception is left to
    propagate, matching every other `JobProcessor` in this codebase (queue.py
    already treats an unexpected processor exception as
    ``ErrorCategory.PERMANENT`` -- duplicating that here would just be a
    second, easier-to-drift copy of the same fallback).
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        store: LocalFileStore,
        provider: OCRProvider,
        *,
        settings: RecognitionSettings | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._store = store
        self._provider = provider
        self._settings = settings or RecognitionSettings()
        self._clock = clock or SystemClock()

    @property
    def confidence_threshold(self) -> float:
        """The Recognition Confidence threshold this instance reads with.

        Since Issue #158 this processor compares it against **each token**,
        to decide which spans came back unreadable, rather than against one
        aggregate for the whole reading; the value and its single source are
        unchanged, and `GradingJobProcessor` still compares the AI grader's
        own single recognition confidence against it.

        Public so `auto_scoring.jobs.grading_processor.GradingJobProcessor`
        (which composes this processor for the recognition half of a job)
        can gate its own additional recognition-confidence checks -- e.g.
        the AI grader's own corrected reading -- against the exact same,
        single-sourced threshold, instead of a second, independently
        configured value that could silently drift from this one (Issue #20
        review: recognition confidence must never be compared against a
        grading threshold or a differently-configured recognition threshold).
        """
        return self._settings.confidence_threshold

    async def process(self, job: Job) -> ProcessingResult:
        question_id = job.question_id
        if question_id is None:
            return ProcessingResult(
                outcome=ProcessingOutcome.FAILED,
                error_category=ErrorCategory.PERMANENT,
                error_message="recognition requires a question_id",
            )

        recognition_id = recognition_result_id(job)
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            existing = uow.recognitions.get(recognition_id)
            if existing is not None:
                return ProcessingResult(
                    outcome=ProcessingOutcome.SUCCEEDED,
                    usable=not _nothing_readable(existing.boxes),
                )
            images = uow.answer_images.list_for_submission(job.submission_id)
            image = find_answer_image(images, question_id)
            if image is None:
                return ProcessingResult(
                    outcome=ProcessingOutcome.FAILED,
                    error_category=ErrorCategory.PERMANENT,
                    error_message="no answer image recorded for this question",
                )
            if image.status is AnswerImageStatus.NEEDS_REVIEW:
                # The crop itself could not be trusted (Issue #17 §7.1) -- do
                # not spend an external call recognizing the wrong region.
                # No RecognitionResult exists yet for this attempt; a human
                # reviews the original page image and either corrects the
                # crop or enters text manually (Issue #19 acceptance).
                # Carries the crop's own reason word, for the same reason
                # `jobs.grading_processor` does (Issue #164): a job that did
                # nothing has to say so on its own row.
                return ProcessingResult(
                    outcome=ProcessingOutcome.SUCCEEDED,
                    usable=False,
                    skipped_reason=image.reason or "answer_image_needs_review",
                )
            image_bytes = self._store.read_bytes(Path(image.image_path))

        # The provider call happens outside the transaction above (and, via
        # to_thread, off the event loop): a real adapter's network round trip
        # must never hold a DB transaction open across it, matching
        # `auto_scoring.jobs.queue`'s own rule for `JobProcessor.process`.
        try:
            result = await to_thread(self._provider.recognize, image_bytes, language=_LANGUAGE)
        except OCRUnavailable:
            # This host has no OCR at all (Issue #114). Not a failure: design
            # section 24 says grading carries on without a reading ("OCR失敗:
            # **採点は止めない。**"), and section 8.1.4 forbids writing a
            # confidence number for something nothing read. So no
            # `RecognitionResult` is persisted, and ``usable`` is True --
            # meaning "there is no OCR term to gate on here", not "the
            # reading was good". `jobs.grading_processor.GradingJobProcessor`
            # -- the only processor this one is composed into -- then decides
            # the question entirely from the grading half, which is exactly
            # what business-rules-and-evaluation-data.md section 4.3 calls
            # for once OCR text is no longer guaranteed to exist.
            #
            # Listed before the sibling clauses below because `OCRUnavailable`
            # descends from `OCRProviderError` too; it is the one member of
            # that hierarchy that does not mean "this call failed".
            return ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True)
        except OCRTimeoutError:
            return self._failed(ErrorCategory.TIMEOUT, "timed out")
        except OCRRateLimitedError as exc:
            return self._failed(ErrorCategory.RATE_LIMITED, "rate limited", exc)
        except OCRServerError:
            return self._failed(ErrorCategory.SERVER_ERROR, "server error")
        except OCRResponseSchemaError:
            return self._failed(ErrorCategory.PERMANENT, "returned a malformed response")
        except OCRProviderError:
            return self._failed(ErrorCategory.PERMANENT, "call failed")

        unreadable = unreadable_spans(
            result, minimum_confidence=self._settings.confidence_threshold
        )
        recognition = RecognitionResult(
            id=recognition_id,
            submission_id=job.submission_id,
            question_id=question_id,
            source=GradingSource.AI,
            text=result.text,
            # Display only, and no longer compared against anything: the
            # worst span's own confidence, kept next to the reading the
            # reviewer can see (`domain.ocr.lowest_token_confidence`).
            confidence=lowest_token_confidence(result),
            created_at=self._clock.now(),
            boxes=_to_domain_boxes(result.tokens, unreadable),
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            uow.recognitions.add(recognition)
            uow.commit()

        return ProcessingResult(
            outcome=ProcessingOutcome.SUCCEEDED,
            usable=not unreadable.nothing_readable,
        )

    def _failed(
        self,
        category: ErrorCategory,
        reason: str,
        failure: OCRProviderError | None = None,
    ) -> ProcessingResult:
        # Never includes the provider exception's own message: it may be
        # built from the request/response body a concrete adapter received,
        # which must never reach `Job.last_error` (AGENTS.md "Security").
        return ProcessingResult(
            outcome=ProcessingOutcome.FAILED,
            error_category=category,
            error_message=f"{self._provider.name} OCR provider {reason}",
            # Only ever non-None for a RATE_LIMITED `OCRRateLimitedError`
            # carrying a parsed `Retry-After` (Issue #153); every other
            # caller either passes no `failure` or one whose
            # `retry_after_seconds` is `None`, and `ProcessingResult.
            # __post_init__` refuses a non-None value outside RATE_LIMITED.
            retry_after_seconds=getattr(failure, "retry_after_seconds", None),
        )
