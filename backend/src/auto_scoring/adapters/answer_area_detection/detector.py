"""`AnswerAreaDetector` over one image-carrying provider call (Issue #105).

The call itself -- which vendor, how the pages are encoded, how the strict
JSON Schema is sent, and what happens to a response that is not a usable
completion envelope -- is `adapters.ai.image_call`, shared with the
criteria-extraction and classification adapters (Issue #125). What stays here
is the part that is about 回答欄 and nothing else: which prompt and per-test
schema go out, and which parser the answer has to satisfy.

Why an image call and not the whole grading chain: ``codex_app_server`` has
no image input at all, and the page image is the only input detection has
(all 11 measured 生徒答案 PDFs have an empty text layer).

**429 is retried here, not left to the reviewer whose click started the call
(Issue #304).** A person is watching this screen, and grading's job queue
already decided (Issue #153) that a ``Retry-After`` is honoured rather than
thrown away; detection sat outside that decision. The retry reuses
`domain.retry_policy.RetryPolicy` -- no second backoff dialect -- and is
bounded two ways so the click cannot hang: a hard attempt cap and a cap on the
*total* wait, and a provider ``Retry-After`` larger than that budget is not
waited out at all. The chosen numbers and why they are safe for a synchronous
call are recorded in docs/ai-grading-pipeline.md (Issue #304). Only
`ProviderRateLimitedError` is retried: a timeout here is one call carrying
every page and can already have burned 300 seconds, so retrying it would make
the reviewer wait for the worst case twice over.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from auto_scoring.adapters.ai.image_call import ImageJsonCall, parse_or_violate
from auto_scoring.adapters.answer_area_detection._prompt import (
    ANSWER_AREA_SYSTEM_INSTRUCTIONS,
    build_answer_area_user_content,
    strict_answer_area_detection_schema,
)
from auto_scoring.domain.ai_provider import ProviderRateLimitedError
from auto_scoring.domain.answer_area_detection import (
    AnswerAreaDetectionOutput,
    AnswerAreaDetectionRequest,
    parse_answer_area_detection,
)
from auto_scoring.domain.models import ErrorCategory
from auto_scoring.domain.retry_policy import RetryPolicy

#: Matches the criteria extractor's own timeout rather than the grading
#: adapters' 120s: this is one call carrying every page of a sheet, started
#: by a person watching a screen, where a grading call carries one cropped
#: answer. Measured sheets run 1-3 pages.
DEFAULT_TIMEOUT_SECONDS = 300.0

#: The name the OpenAI-compatible ``response_format`` gives this schema.
SCHEMA_NAME = "answer_area_detection"

#: How many attempts (1 initial + retries) one synchronous detection call may
#: make on a 429 before the reviewer is told to try again later. Measured
#: detection runs 13-21 seconds when it succeeds, so the point of the retry is
#: to absorb a momentary congestion window, not to wait out a long quota.
DETECT_RATE_LIMIT_MAX_ATTEMPTS = 3

#: The backoff schedule and wait budget this adapter retries a 429 with.
#: ``max_attempts`` is the hard cap enforced below; the rate-limited budget is
#: a second, independent stop: once the *actual* waits already spent plus the
#: next delay would cross it, the call gives up rather than sleeping past it.
#: ``delay_for`` honours a provider ``Retry-After`` exactly, and an
#: ``Retry-After`` larger than the budget is refused outright by
#: `should_retry`, so this is an upper bound on how long a click can hang.
DETECT_RETRY_POLICY = RetryPolicy(
    max_attempts=DETECT_RATE_LIMIT_MAX_ATTEMPTS,
    rate_limited_initial_backoff_seconds=4.0,
    rate_limited_backoff_multiplier=2.0,
    rate_limited_max_backoff_seconds=16.0,
    rate_limited_budget_seconds=20.0,
)


class StructuredAnswerAreaDetector:
    """Reads one answer sheet's pages per ``detect()``.

    A response that does not satisfy
    :class:`~auto_scoring.domain.answer_area_detection.AnswerAreaDetectionOutput`
    is discarded (`adapters.ai.image_call.discard_response`) -- never turned
    into a partial reading, which would put boxes on a page the model never
    actually placed there.
    """

    def __init__(
        self,
        call: ImageJsonCall,
        *,
        retry_policy: RetryPolicy = DETECT_RETRY_POLICY,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._call = call
        self._retry_policy = retry_policy
        # Injected so a test can drive the retry loop without waiting, exactly
        # as `domain.retry_policy` takes its jitter and clock from outside.
        self._sleep = sleep

    @property
    def name(self) -> str:
        return self._call.provider

    def detect(self, request: AnswerAreaDetectionRequest) -> AnswerAreaDetectionOutput:
        attempt = 1
        waited = 0.0
        while True:
            try:
                return self._detect_once(request)
            except ProviderRateLimitedError as exc:
                if attempt >= self._retry_policy.max_attempts:
                    raise
                if not self._retry_policy.should_retry(
                    category=ErrorCategory.RATE_LIMITED,
                    attempts=attempt,
                    retry_after_seconds=exc.retry_after_seconds,
                ):
                    raise
                delay = self._retry_policy.delay_for(
                    category=ErrorCategory.RATE_LIMITED,
                    attempt=attempt,
                    retry_after_seconds=exc.retry_after_seconds,
                )
                # Cap the *actual* wait, not only the nominal schedule:
                # `should_retry` bounds the nominal delays, but a provider
                # `Retry-After` replaces a delay outright and several of them
                # could otherwise add up past the budget across retries.
                if waited + delay > self._retry_policy.rate_limited_budget_seconds:
                    raise
                self._sleep(delay)
                waited += delay
                attempt += 1

    def _detect_once(self, request: AnswerAreaDetectionRequest) -> AnswerAreaDetectionOutput:
        text, _ = self._call.call(
            system=ANSWER_AREA_SYSTEM_INSTRUCTIONS,
            user_text=build_answer_area_user_content(request),
            images=request.page_images,
            schema=strict_answer_area_detection_schema(request.question_numbers),
        )
        return parse_or_violate(
            text,
            lambda body: parse_answer_area_detection(
                body,
                question_numbers=request.question_numbers,
                page_count=len(request.page_images),
                boxes_per_page=[len(boxes) for boxes in request.page_boxes],
            ),
            label=self._call.label,
            schema_name="AnswerAreaDetectionOutput",
        )
