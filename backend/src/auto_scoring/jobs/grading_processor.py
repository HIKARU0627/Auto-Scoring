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

import logging
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
    ProviderAttempt,
    ProviderFailure,
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
    AnswerImageFinding,
    AnswerImageStatus,
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
from auto_scoring.domain.review_workflow import (
    resolve_effective_grade,
    resolve_effective_recognition,
)
from auto_scoring.domain.submission_intake import NOT_THE_ANSWER_CROP_REASON
from auto_scoring.jobs.clock import Clock, SystemClock
from auto_scoring.jobs.grading_settings import GradingSettings
from auto_scoring.jobs.recognition_processor import RecognitionJobProcessor, recognition_result_id

logger = logging.getLogger(__name__)


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

    **On a host with no OCR the first of the three drops out** rather than
    being failed against a fabricated 0.0 (Issue #114). It has to: this is
    also the shape of a question whose answer is a formula or a diagram,
    which design section 8.1.4 says OCR cannot read at all and must not be
    given a confidence number for. `RecognitionJobProcessor` reports
    ``usable=True`` there meaning "no OCR term to gate on", so what remains
    is the grading AI's own reading and its grading confidence -- exactly
    the substitution business-rules-and-evaluation-data.md section 4.3
    prescribes ("**OCR テキストとは限らない。**... 採点 AI 自身の読み取りが
    引き継ぐ対象になる場合がある"). An OCR that *did* read the answer and was
    not confident still blocks, unchanged: section 4.4 was written for that
    case, and this leaves it alone.

    Grading is skipped -- without ever calling `AIProvider` -- when there is
    nothing to grade: an untrusted crop (`AnswerImageStatus.NEEDS_REVIEW` --
    the image, not the reading, is what cannot be trusted), no registered
    model answer, or no rubric. The last two surface as
    `ProcessingOutcome.FAILED` (`ErrorCategory.PERMANENT`), the same
    "insufficient setup" treatment `RecognitionJobProcessor` already gives a
    missing answer image -- a human must register the missing material, not
    have the AI guess it (AGENTS.md "Verification": "読めない文字や判断不能
    を推測で補完しない").

    A fourth "nothing to grade" case can only be recognized *after* the
    call: the grader reports that the image it was given is not this
    question's answer (`AnswerImageFinding.NOT_THE_ANSWER`, Issue #136).
    That response produces no `GradeResult` at all -- see
    `_crop_is_not_the_answer` -- because a score computed from the wrong
    piece of paper is indistinguishable on screen from a correct one, which
    is how half of one real run's grades came to be wrong 0s at confidence
    1.00.
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
            images = uow.answer_images.list_for_submission(job.submission_id)
            image = find_answer_image(images, question_id)
            assert image is not None  # the recognition step above already required this
            if image.status is AnswerImageStatus.NEEDS_REVIEW:
                # The crop itself could not be trusted (Issue #17 section 7.1).
                # The recognition step already declined to send it anywhere,
                # and grading a region that may not be this question's answer
                # at all would be worse than not grading it -- a human
                # corrects the crop or types the text in.
                #
                # Checked on the image rather than on "no RecognitionResult
                # was persisted", which used to stand in for it: since Issue
                # #114 an absent row also means "this host has no OCR", and
                # that one must go on to grade.
                #
                # ``usable=False`` explicitly, rather than passing
                # ``recognition_outcome`` through (Issue #136). Until this
                # Issue a crop could only be NEEDS_REVIEW from intake --
                # before any OCR row existed -- so the recognition half
                # always reported ``usable=False`` here anyway. Now a crop
                # can be flagged *after* it has been read and graded
                # (`_crop_is_not_the_answer`), and on the next attempt the
                # recognition half finds its own earlier, confident row and
                # reports ``usable=True``. Passing that on would release a
                # dependent question onto a prerequisite that has no grade
                # at all, on the strength of having been read clearly --
                # which is precisely what "the crop cannot be trusted"
                # denies.
                #
                # ``skipped_reason`` carries the crop's own reason word
                # (Issue #164). Until it did, this branch produced a job row
                # saying ``succeeded``, ``last_error`` NULL, in 0.013
                # seconds -- 23 of one real run's 37 grading jobs, none of
                # them distinguishable from work that was actually done. The
                # value is `AnswerImage.reason`'s fixed vocabulary, which
                # `app/lib/core/grading_failure_reason.dart` already reads
                # off ``last_error`` for the same purpose; nothing from the
                # paper goes into it.
                return ProcessingResult(
                    outcome=ProcessingOutcome.SUCCEEDED,
                    usable=False,
                    skipped_reason=image.reason or "answer_image_needs_review",
                )

            recognition = uow.recognitions.get(recognition_result_id(job))
            # An absent row therefore means only that no OCR reading exists
            # (`domain.ocr.OCRUnavailable`). That is an empty ``ocr_text``,
            # not a reason to skip grading: design section 8.1.1 makes the
            # answer-area crop the grading input and the OCR reading merely
            # "得られていれば補助情報として添える", and section 24 says
            # "OCR失敗: **採点は止めない。**"
            ocr_text = recognition.text if recognition is not None else ""

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
                # Resolved through the prerequisite's own review history (Issue
                # #22 P1 review), not simply "prefer the latest human row" --
                # once Undo reverts a prerequisite's human correction, its
                # `RecognitionResult`/`GradeResult` rows are still there
                # (append-only) but must stop feeding a dependent question's
                # grading context, the same way `QuestionReviewState.
                # displayGrade` stops showing them client-side.
                prerequisite_reviews = uow.reviews.history(job.submission_id, prerequisite_id)
                prerequisite_grades = uow.grades.history(job.submission_id, prerequisite_id)
                prerequisite_recognitions = uow.recognitions.history(
                    job.submission_id, prerequisite_id
                )
                sources[prerequisite_id] = PrerequisiteSource(
                    recognition=resolve_effective_recognition(
                        prerequisite_reviews, prerequisite_grades, prerequisite_recognitions
                    ),
                    grade=resolve_effective_grade(prerequisite_reviews, prerequisite_grades),
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

            image_bytes = self._store.read_bytes(Path(image.image_path))
            rubric_text, criterion_ids = build_rubric_prompt(
                question.scoring_method, rubric.criteria
            )

        request = GradingRequest(
            question_id=question_id,
            prompt_text=_prompt_text_for(question.number),
            answer_image=image_bytes,
            ocr_text=ocr_text,
            model_answer=model_answer,
            rubric_text=rubric_text,
            criterion_ids=criterion_ids,
            max_score=question.points,
            prerequisite_context=prerequisite_context,
        )

        # The provider call happens outside the transaction above (and, via
        # to_thread, off the event loop) -- mirrors
        # `RecognitionJobProcessor.process`'s own rule for `AIProvider.grade`.
        try:
            response = await to_thread(self._ai_provider.grade, request)
        except ProviderTimeoutError as exc:
            return self._failed(ErrorCategory.TIMEOUT, "timed out", exc)
        except ProviderRateLimitedError as exc:
            return self._failed(ErrorCategory.RATE_LIMITED, "rate limited", exc)
        except ProviderServerError as exc:
            return self._failed(ErrorCategory.SERVER_ERROR, "server error", exc)
        except SchemaViolation as exc:
            return self._failed(ErrorCategory.PERMANENT, "returned a malformed response", exc)
        except ProviderUnavailable as exc:
            return self._failed(ErrorCategory.PERMANENT, "call failed", exc)

        response_criterion_ids = {c.criterion_id for c in response.criteria}
        if response.max_score != question.points or response_criterion_ids != set(criterion_ids):
            # A schema-valid response whose max score is not this question's,
            # or whose criteria don't correspond 1:1 to the registered rubric
            # (a registered criterion silently omitted, since Issue #117 the
            # only way this set can differ) -- never scored as if it were a
            # real grade (mirrors `ai_grading_metrics.evaluate_sample`'s
            # "mismatched" handling in the PoC 2 harness this pipeline
            # adopted; extended per Issue #20 review to also cover criteria
            # that don't map onto the rubric, not just max_score).
            #
            # There is no ``response.question_id != question_id`` check any
            # more: since Issue #117 that field is filled in from *this*
            # request rather than copied out of the response, so comparing
            # it to itself could only ever pass. What it used to catch -- a
            # model writing a subtly different id -- is now impossible by
            # construction instead of caught after the fact.
            return self._failed(ErrorCategory.PERMANENT, "returned a mismatched response")

        if response.answer_image_finding is AnswerImageFinding.NOT_THE_ANSWER:
            # The grader says the image it was given is not this question's
            # answer (Issue #136). Nothing derived from it can be believed --
            # including the score, and including a score above 0: a response
            # that says both is contradictory, and there is no reading of it
            # under which the number is worth keeping. So no `GradeResult` is
            # written at all, and the question goes to a human.
            #
            # This is the failure this Issue exists for. On a real 8-subject
            # run, 7 of the 14 grades produced were 0 点 at confidence 1.00
            # against a crop that was not that question's answer, and the
            # screen showed them exactly like a correct 0. A grade row is
            # what makes them look alike; not writing one is what stops it.
            #
            # Deliberately *not* the same as "the crop looks blank"
            # (`AnswerImageFinding.BLANK`, `is_nearly_blank_crop`): a blank
            # answer area is an ordinary thing a student produces and its 0
            # may well be right. Only the claim that the image shows
            # something else acts here.
            return self._crop_is_not_the_answer(job, question_id)

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
            # Only ever ``answer``/``blank``/``None`` here: the
            # ``not_the_answer`` case returned above without producing a
            # grade, and `GradeResult` plus the DB trigger both refuse to
            # store it. ``blank`` is recorded and otherwise
            # ignored on purpose -- see `AnswerImageFinding`.
            answer_image_finding=response.answer_image_finding,
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

    def _crop_is_not_the_answer(self, job: Job, question_id: str) -> ProcessingResult:
        """Record the grader's verdict on the crop, and fail the job.

        Two records, because they answer two different questions:

        * the crop's own row moves to `AnswerImageStatus.NEEDS_REVIEW` with
          `NOT_THE_ANSWER_CROP_REASON` -- a durable property of that crop, in
          the same vocabulary intake already writes when *it* can tell the
          crop is unusable. It is also what makes a re-run cost nothing:
          both this processor and `jobs.recognition_processor` stop on a
          NEEDS_REVIEW image without calling any provider, and the same
          image would only earn the same verdict again.
        * the job fails ``PERMANENT`` -- retrying re-sends the identical
          bytes to the identical model, so there is nothing to retry. This
          is the same treatment a missing rubric or model answer already
          gets: the AI cannot proceed until a person fixes the material.
          `Job.last_error` carries the reason to the review screen (the
          message is this method's own literals -- no provider text, no
          student content), where the app matches on it to say *what* to
          fix: the 回答欄 the crop came from, not the score.
        """
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            uow.answer_images.mark_needs_review(
                job.submission_id, question_id, NOT_THE_ANSWER_CROP_REASON
            )
            uow.commit()
        return self._failed(
            ErrorCategory.PERMANENT,
            "reported that the answer image is not this question's answer "
            f"({NOT_THE_ANSWER_CROP_REASON})",
        )

    def _failed(
        self,
        category: ErrorCategory,
        reason: str,
        failure: ProviderFailure | None = None,
    ) -> ProcessingResult:
        # Never includes a provider exception's own message: it may be built
        # from the request/response body (which can contain OCR'd student
        # answer text), which must never reach `Job.last_error` (AGENTS.md
        # "Security").
        #
        # What it does include, since Issue #97 review round 4, is
        # ``failure``'s `ProviderAttempt` records: provider *id*, exception
        # class, HTTP status number -- assembled from literals and numbers
        # rather than filtered out of free text. Without them the whole
        # chain dying reads as "call failed", and a first launch that needs
        # `gcloud auth application-default login` (401) is indistinguishable
        # from one that needs the API enabled (403) or a corrected
        # ``AUTO_SCORING_GEMINI_MODEL`` (404). This is the one place that
        # survives to the API and the screen: on a total failure there is no
        # `GradeResult` to carry the provider triple.
        message = f"{self._ai_provider.name} AI provider {reason}"
        diagnosis = _diagnosis(failure, provider_name=self._ai_provider.name)
        if diagnosis:
            message = f"{message} [{diagnosis}]"
        # The same string, to the log as well as to `Job.last_error` (Issue
        # #121). `FallbackAIProvider` already logs one line per link it falls
        # through, but a host configured with a single provider never builds
        # a chain at all -- and that is exactly the shape the live run had,
        # which is why a whole afternoon of permanent failures left no trace
        # in the sidecar log. Safe by construction: `message` is this
        # method's own literals plus `_diagnosis`.
        logger.warning("%s", message)
        return ProcessingResult(
            outcome=ProcessingOutcome.FAILED,
            error_category=category,
            error_message=message,
        )


def _diagnosis(failure: ProviderFailure | None, *, provider_name: str) -> str:
    """The failed call(s) rendered for `Job.last_error`.

    A chain reports every link it tried (`FallbackAIProvider` fills
    ``attempts``) -- "the last one failed" alone cannot say that Vertex was
    403 before OpenRouter was 401. A single adapter reports none, so the one
    attempt is reconstructed here from what this processor already knows: the
    provider it called, and the exception class it got back.
    """
    if failure is None:
        return ""
    attempts = failure.attempts or (
        ProviderAttempt(
            provider=provider_name,
            error=type(failure).__name__,
            status_code=failure.status_code,
            detail=failure.detail,
        ),
    )
    return "; ".join(str(attempt) for attempt in attempts)


_SCORING_METHOD_LABEL = {
    ScoringMethod.ADDITIVE: "加算方式(各criterionの得点を合計して満点内に収める)",
    ScoringMethod.SUBTRACTIVE: "減点方式(満点から各criterionの減点を差し引く)",
}


def build_rubric_prompt(
    scoring_method: ScoringMethod, criteria: Sequence[RubricCriterion]
) -> tuple[str, tuple[str, ...]]:
    """The rubric text sent to the provider, and the registered criterion ids
    that text's numbering stands for.

    Returned together, from one ordered read of ``criteria``, because they
    are two halves of one correspondence: the prompt says 「1. ...」 and the
    response answers ``index: 1``, and if the numbering and the id list were
    built in two places they could drift into scoring the wrong criterion
    silently. Ordered by `RubricCriterion.position` -- the rubric's own
    registered order, not whatever order a repository happened to return.

    Carries the question's `scoring_method` so the provider knows whether to
    grade additively or apply `SUBTRACTIVE` deductions (Issue #20 review,
    P1: omitting it left a real provider unable to reproduce the registered
    rubric from the description text alone).

    It deliberately does **not** carry the criteria's registered ids any
    more (Issue #117). It used to send ``- id=<45 chars>: ...`` and ask for
    that string back; on real material a model duplicated one character of
    it 4 times out of 4 and every one of those gradings failed
    ``PERMANENT``. A number is not a transcription, so this sends numbers.
    """
    ordered = sorted(criteria, key=lambda c: c.position)
    lines = [f"採点方式: {_SCORING_METHOD_LABEL[scoring_method]}"]
    lines.extend(
        f"{position}. {c.description}(配点{c.max_points}点)"
        for position, c in enumerate(ordered, start=1)
    )
    return "\n".join(lines), tuple(c.id for c in ordered)


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
