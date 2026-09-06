"""`JobProcessor` for the grading half of Issue #18's per-question job
(docs/job-queue.md: "1 Question = 1 Job(JobKind.GRADING)... 個々のJobの内部で
OCR→採点をどう分けるかはJobProcessor実装側の自由").

Composes `auto_scoring.jobs.recognition_processor.RecognitionJobProcessor`
for the OCR half (Issue #19, unchanged) and adds the `AIProvider` grading
half Issue #19 left as "対象外" (out of scope) for a later Issue -- this one
(GitHub Issue #20; docs/ai-grading-pipeline.md has the full design record).

Framework-adjacent, not domain: this is the concrete boundary the `domain.
ai_provider.AIProvider` and `domain.job_execution.JobProcessor` ports plug
into, mirroring `jobs.recognition_processor`'s own place in the architecture.
"""

from __future__ import annotations

from asyncio import to_thread
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.ai_provider import (
    AIProvider,
    GradingRequest,
    ProviderRateLimitedError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailable,
    SchemaViolation,
)
from auto_scoring.domain.grading_context import (
    MissingPrerequisiteContextError,
    PrerequisiteSource,
    build_context_entries,
    build_prerequisite_context,
)
from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import (
    Annotation,
    CriterionResult,
    ErrorCategory,
    GradeResult,
    GradingSource,
    Job,
    RecognitionResult,
    RubricCriterion,
    Score,
    ScoringMethod,
    find_answer_image,
)
from auto_scoring.jobs.clock import Clock, SystemClock
from auto_scoring.jobs.grading_settings import GradingSettings
from auto_scoring.jobs.recognition_processor import RecognitionJobProcessor, recognition_result_id


def grade_result_id(job: Job) -> str:
    """Deterministic id for the `GradeResult` a successful grading of ``job``
    produces -- mirrors `recognition_result_id`'s own reasoning (idempotent
    replay after a crash between persisting the row and the queue recording
    SUCCEEDED must not call the provider a second time or add a duplicate
    proposal).
    """
    return f"grade:{job.id}"


def grading_recognition_id(job: Job) -> str:
    """Deterministic id for the `RecognitionResult` that records the AI
    grader's *own* reading of the answer (Issue #20 review, P1): a
    multimodal `AIProvider` may correct the OCR text it was given
    (`AIProviderContract` explicitly allows this), and that corrected
    reading -- with its own, possibly lower, confidence -- must not be
    silently discarded. Distinct from `recognition_result_id(job)` (the OCR
    pipeline's own reading, Issue #19) so both are visible side by side in
    review history, matching simplified-design-specification.md section
    16.5's "AI認識文字" review-UI field.
    """
    return f"grading-recognition:{job.id}"


def _latest_preferring_human[T](results: Sequence[tuple[GradingSource, T]]) -> T | None:
    """Pick the latest result, preferring a human confirmation over an AI
    proposal regardless of recency (a human correction always supersedes an
    AI reading for context purposes, mirroring the general "human overrides
    AI" rule -- simplified-design-specification.md section 19).

    ``results`` is already in ascending ``created_at`` order (matches every
    ``history()`` repository method's ordering), so "the latest of a source"
    is simply the last matching entry.
    """
    human = [value for source, value in results if source is GradingSource.HUMAN]
    if human:
        return human[-1]
    ai = [value for source, value in results if source is GradingSource.AI]
    return ai[-1] if ai else None


class GradingJobProcessor:
    """Recognizes (via `RecognitionJobProcessor`) and then AI-grades one
    question's answer, persisting a `GradeResult` (source=AI, always -- Issue
    #20 acceptance: never auto-confirm) and any AI-proposed annotations.

    ``usable`` on a `ProcessingResult.SUCCEEDED` outcome requires **all
    three** of: the OCR pipeline's own Recognition Confidence
    (`recognition_outcome.usable`, at `RecognitionJobProcessor`'s
    threshold), the AI grader's *own* Recognition Confidence in whatever
    text it actually graded (`response.recognition_confidence`, at the same
    threshold -- a multimodal provider may correct the OCR reading, and its
    confidence in that corrected reading must gate too, not just the OCR
    pipeline's), and Grading Confidence (at `GradingSettings`'s own,
    separate threshold) -- Issue #20 acceptance: "Recognition Confidenceと
    Grading Confidenceのどちらかが閾値未満ならneeds_reviewにする". A
    dependent question stays `BLOCKED` unless all three hold.

    Grading is skipped -- without ever calling `AIProvider` -- when there is
    nothing to grade: no answer text at all (the recognition step itself
    could not run, e.g. an untrusted crop), no registered model answer, or no
    rubric. These surface as `ProcessingOutcome.FAILED`
    (`ErrorCategory.PERMANENT`), the same "insufficient setup" treatment
    `RecognitionJobProcessor` already gives a missing answer image -- a human
    must register the missing material, not have the AI guess it
    (AGENTS.md "Verification": "読めない文字や判断不能を推測で補完しない").
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        store: LocalFileStore,
        recognition_processor: RecognitionJobProcessor,
        ai_provider: AIProvider,
        *,
        grading_settings: GradingSettings | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._store = store
        self._recognition = recognition_processor
        self._ai_provider = ai_provider
        self._settings = grading_settings or GradingSettings()
        self._clock = clock or SystemClock()

    async def process(self, job: Job) -> ProcessingResult:
        recognition_outcome = await self._recognition.process(job)
        if recognition_outcome.outcome is ProcessingOutcome.FAILED:
            return recognition_outcome

        question_id = job.question_id
        assert question_id is not None  # RecognitionJobProcessor already required this

        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            recognition = uow.recognitions.get(recognition_result_id(job))
            if recognition is None:
                # The crop itself could not be trusted (no RecognitionResult
                # was ever persisted for this attempt) -- there is no answer
                # text to grade at all.
                return recognition_outcome

            existing_grade = uow.grades.get(grade_result_id(job))
            if existing_grade is not None:
                # Persisted atomically with existing_grade (same commit,
                # below) on the successful attempt that produced it.
                existing_grading_recognition = uow.recognitions.get(grading_recognition_id(job))
                assert existing_grading_recognition is not None
                return ProcessingResult(
                    outcome=ProcessingOutcome.SUCCEEDED,
                    usable=(
                        recognition_outcome.usable
                        and existing_grading_recognition.confidence
                        >= self._recognition.confidence_threshold
                        and existing_grade.confidence >= self._settings.confidence_threshold
                    ),
                )

            question = uow.questions.get(question_id)
            if question is None:
                return self._failed(ErrorCategory.PERMANENT, "question not found")
            model_answer = question.model_answer
            if not model_answer or not model_answer.strip():
                return self._failed(
                    ErrorCategory.PERMANENT, "grading requires a registered model answer"
                )
            rubric = uow.rubrics.get_for_question(question_id)
            if rubric is None or not rubric.criteria:
                return self._failed(ErrorCategory.PERMANENT, "grading requires a rubric")

            submission = uow.submissions.get(job.submission_id)
            if submission is None:
                return self._failed(ErrorCategory.PERMANENT, "submission not found")
            graph = uow.dependency_graphs.get_latest_confirmed(submission.test_id)
            if graph is None:
                # submit_submission already requires a confirmed graph to
                # create any job at all -- should not happen in practice.
                return self._failed(
                    ErrorCategory.PERMANENT, "no confirmed dependency graph for this test"
                )

            prerequisite_ids = sorted(
                {
                    edge.from_question_id
                    for edge in graph.edges
                    if edge.to_question_id == question_id
                }
            )
            sources: dict[str, PrerequisiteSource] = {}
            for prerequisite_id in prerequisite_ids:
                prerequisite_recognition = _latest_preferring_human(
                    [
                        (r.source, r)
                        for r in uow.recognitions.history(job.submission_id, prerequisite_id)
                    ]
                )
                prerequisite_grade = _latest_preferring_human(
                    [(g.source, g) for g in uow.grades.history(job.submission_id, prerequisite_id)]
                )
                sources[prerequisite_id] = PrerequisiteSource(
                    recognition=prerequisite_recognition, grade=prerequisite_grade
                )

            try:
                prerequisite_context = build_prerequisite_context(
                    graph, question_id, sources=sources
                )
            except MissingPrerequisiteContextError:
                # A confirmed edge calls for prerequisite data this call
                # could not find -- should not happen given DAG scheduling
                # gates a dependent's own Job on every prerequisite being
                # usable first, but treated as a setup failure rather than
                # ever fabricating the missing context.
                return self._failed(ErrorCategory.PERMANENT, "prerequisite context unavailable")
            context_entries = build_context_entries(graph, question_id, sources=sources)

            images = uow.answer_images.list_for_submission(job.submission_id)
            image = find_answer_image(images, question_id)
            assert image is not None  # the recognition step above already required this
            image_bytes = self._store.read_bytes(Path(image.image_path))
            rubric_text = _rubric_text_for(question.scoring_method, rubric.criteria)

        request = GradingRequest(
            question_id=question_id,
            prompt_text=_prompt_text_for(question.number),
            answer_image=image_bytes,
            ocr_text=recognition.text,
            model_answer=model_answer,
            rubric_text=rubric_text,
            max_score=question.points,
            prerequisite_context=prerequisite_context,
        )

        # The provider call happens outside the transaction above (and, via
        # to_thread, off the event loop) -- mirrors
        # `RecognitionJobProcessor.process`'s own rule for `AIProvider.grade`.
        try:
            response = await to_thread(self._ai_provider.grade, request)
        except ProviderTimeoutError:
            return self._failed(ErrorCategory.TIMEOUT, "timed out")
        except ProviderRateLimitedError:
            return self._failed(ErrorCategory.RATE_LIMITED, "rate limited")
        except ProviderServerError:
            return self._failed(ErrorCategory.SERVER_ERROR, "server error")
        except SchemaViolation:
            return self._failed(ErrorCategory.PERMANENT, "returned a malformed response")
        except ProviderUnavailable:
            return self._failed(ErrorCategory.PERMANENT, "call failed")

        rubric_criterion_ids = {c.id for c in rubric.criteria}
        response_criterion_ids = {c.criterion_id for c in response.criteria}
        if (
            response.question_id != question_id
            or response.max_score != question.points
            or response_criterion_ids != rubric_criterion_ids
        ):
            # A schema-valid response for the wrong question, or one whose
            # criteria don't correspond 1:1 to the registered rubric (an
            # unknown criterion id, or a registered one silently omitted) --
            # never scored as if it were a real grade (mirrors
            # `ai_grading_metrics.evaluate_sample`'s "mismatched" handling in
            # the PoC 2 harness this pipeline adopted; extended per Issue #20
            # review to also cover criteria that don't map onto the rubric,
            # not just question_id/max_score).
            return self._failed(ErrorCategory.PERMANENT, "returned a mismatched response")

        now = self._clock.now()
        grade = GradeResult(
            id=grade_result_id(job),
            submission_id=job.submission_id,
            question_id=question_id,
            source=GradingSource.AI,
            score=Score(awarded=response.score, maximum=response.max_score),
            confidence=response.grading_confidence,
            criteria=tuple(
                CriterionResult(
                    criterion_id=c.criterion_id, outcome=c.outcome, confidence=c.confidence
                )
                for c in response.criteria
            ),
            rationale=response.rationale,
            comment=response.comment,
            provider=response.descriptor.provider,
            model=response.descriptor.model,
            prompt_version=response.descriptor.prompt_version,
            dependency_graph_version=graph.version,
            context=context_entries,
            created_at=now,
        )
        # The grader's own recognition reading (Issue #20 review, P1): a
        # multimodal provider may have corrected the OCR text it was given,
        # and its own confidence in that reading -- not just the OCR
        # pipeline's -- must gate `usable` and be visible in review history,
        # never silently dropped in favor of only the pre-existing OCR
        # RecognitionResult.
        grading_recognition = RecognitionResult(
            id=grading_recognition_id(job),
            submission_id=job.submission_id,
            question_id=question_id,
            source=GradingSource.AI,
            text=response.recognition_text,
            confidence=response.recognition_confidence,
            created_at=now,
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            uow.grades.add(grade)
            uow.recognitions.add(grading_recognition)
            for candidate in response.annotations:
                uow.annotations.add(
                    Annotation(
                        id=str(uuid4()),
                        submission_id=job.submission_id,
                        question_id=question_id,
                        source=GradingSource.AI,
                        kind=candidate.type,
                        anchor_text=candidate.target,
                        comment=candidate.comment,
                        created_at=now,
                    )
                )
            uow.commit()

        return ProcessingResult(
            outcome=ProcessingOutcome.SUCCEEDED,
            usable=(
                recognition_outcome.usable
                and response.recognition_confidence >= self._recognition.confidence_threshold
                and response.grading_confidence >= self._settings.confidence_threshold
            ),
        )

    def _failed(self, category: ErrorCategory, reason: str) -> ProcessingResult:
        # Never includes a provider exception's own message: it may be built
        # from the request/response body (which can contain OCR'd student
        # answer text), which must never reach `Job.last_error` (AGENTS.md
        # "Security").
        return ProcessingResult(
            outcome=ProcessingOutcome.FAILED,
            error_category=category,
            error_message=f"{self._ai_provider.name} AI provider {reason}",
        )


_SCORING_METHOD_LABEL = {
    ScoringMethod.ADDITIVE: "加算方式(各criterionの得点を合計して満点内に収める)",
    ScoringMethod.SUBTRACTIVE: "減点方式(満点から各criterionの減点を差し引く)",
}


def _rubric_text_for(scoring_method: ScoringMethod, criteria: Sequence[RubricCriterion]) -> str:
    """Rubric text sent to the provider (Issue #20 review, P1): must carry
    every criterion's registered ``id`` (not just its description/points) so
    a real provider's response can be mapped back onto the rubric
    unambiguously, and the question's `scoring_method` so it knows whether to
    grade additively or apply `SUBTRACTIVE` deductions -- omitting either
    left a real provider unable to reliably reproduce the registered rubric
    from the description text alone.
    """
    lines = [f"採点方式: {_SCORING_METHOD_LABEL[scoring_method]}"]
    lines.extend(f"- id={c.id}: {c.description}(配点{c.max_points}点)" for c in criteria)
    return "\n".join(lines)


def _prompt_text_for(question_number: str) -> str:
    """Placeholder problem-statement text (docs/ai-grading-pipeline.md
    "prompt_text placeholder").

    The MVP question record (Issue #11) does not yet store the 問題文 text
    extracted from an exam-paper PDF -- that extraction pipeline is a
    separate, not-yet-built piece (see docs/dependency-graph.md's identical
    open item for `QuestionInfo.prompt_text`). Rather than fabricate exam
    content or leave `GradingRequest.prompt_text` blank (rejected at
    construction -- a blank prompt sent to a real provider would be
    meaningless), this names only the question number: an honest instruction,
    not invented academic content. The real grading signal (`model_answer`,
    `rubric_text`) still reaches the provider unabridged.
    """
    return f"設問「{question_number}」の解答を、模範解答と採点基準に基づいて採点してください。"
