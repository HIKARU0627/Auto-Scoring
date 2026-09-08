"""Tests for :class:`FallbackAIProvider` -- the Issue #81 priority chain.

The behaviours pinned here are the ones ``docs/ai-grading-pipeline.md``
"AIモデル: 優先度つきフォールバック" decided, and each of them is load-bearing
for something outside this class: which failures fall through (or a rate
limit would stall the whole job), which exception surfaces when the chain is
exhausted (or the queue would misclassify it), and whose descriptor ends up
on the response (or per-provider agreement metrics would attribute every
grade to the chain instead of the model that produced it).
"""

import logging

import pytest

from auto_scoring.adapters.ai_grading.fallback_provider import FallbackAIProvider
from auto_scoring.domain.ai_provider import (
    AIProvider,
    GradingRequest,
    GradingResponse,
    ProviderAttempt,
    ProviderDescriptor,
    ProviderRateLimitedError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailable,
    SchemaViolation,
)

from .test_ai_provider_contract import _VALID_REQUEST, AIProviderContract


class _StubProvider:
    """Grades successfully, or always raises ``failure``.

    ``question_id == "malformed"`` raises :class:`SchemaViolation` so this
    stub satisfies ``AIProviderContract`` when used as the chain's only
    working link.
    """

    def __init__(self, name: str, failure: Exception | None = None) -> None:
        self.name = name
        self._failure = failure
        self.calls = 0

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.name,
            model=f"{self.name}-model",
            version=None,
            prompt_version="v1",
            temperature=0.0,
            structured_output_mode="json_schema",
        )

    def grade(self, request: GradingRequest) -> GradingResponse:
        self.calls += 1
        if self._failure is not None:
            raise self._failure
        if request.question_id == "malformed":
            raise SchemaViolation("stub returned invalid structured output")
        return GradingResponse(
            question_id=request.question_id,
            recognition_text=request.ocr_text,
            recognition_confidence=0.9,
            score=4,
            max_score=request.max_score,
            grading_confidence=0.8,
            rationale="根拠",
            comment="コメント",
            criteria=(),
            annotations=(),
            descriptor=self.describe(),
            latency_seconds=0.01,
        )


class TestFallbackAIProviderContract(AIProviderContract):
    @pytest.fixture
    def provider(self) -> AIProvider:
        return FallbackAIProvider([_StubProvider("primary")])


@pytest.mark.parametrize(
    "failure",
    [
        ProviderRateLimitedError("429"),
        ProviderServerError("503"),
        ProviderTimeoutError("timeout"),
        SchemaViolation("bad json"),
        ProviderUnavailable("401"),
    ],
)
def test_every_port_failure_falls_through_to_the_next_provider(failure: Exception) -> None:
    """docs/ai-grading-pipeline.md's table plus the bare
    ``ProviderUnavailable`` case: a credential that was valid at
    construction and is rejected at call time is exactly what a chain is
    for."""
    first = _StubProvider("first", failure)
    second = _StubProvider("second")

    response = FallbackAIProvider([first, second]).grade(_VALID_REQUEST)

    assert first.calls == 1  # one attempt each, no in-provider retry
    assert response.descriptor.provider == "second"


def test_the_first_working_provider_wins_and_later_ones_are_never_called() -> None:
    first = _StubProvider("first")
    second = _StubProvider("second")

    FallbackAIProvider([first, second]).grade(_VALID_REQUEST)

    assert (first.calls, second.calls) == (1, 0)


def test_the_successful_child_descriptor_is_returned_unchanged() -> None:
    """Decision record section 3 (B): "どの provider で採点したかを結果に残す".
    The chain must not stamp its own name over the model that graded, or
    ``domain.ai_grading_metrics``' per-provider buckets stop meaning
    anything."""
    chain = FallbackAIProvider(
        [_StubProvider("first", ProviderServerError()), _StubProvider("second")]
    )

    response = chain.grade(_VALID_REQUEST)

    assert response.descriptor.provider == "second"
    assert response.descriptor.model == "second-model"
    assert chain.name == "fallback"


def test_an_exhausted_chain_reraises_the_last_failure_unchanged() -> None:
    """The queue classifies on the exception type
    (``jobs.grading_processor``), so wrapping it -- or replacing it with a
    generic error -- would silently change a retryable rate limit into an
    unknown failure."""
    chain = FallbackAIProvider(
        [
            _StubProvider("first", ProviderServerError("503")),
            _StubProvider("second", ProviderRateLimitedError("429")),
        ]
    )

    with pytest.raises(ProviderRateLimitedError):
        chain.grade(_VALID_REQUEST)


def test_an_all_schema_violation_chain_stays_a_schema_violation() -> None:
    """Which is what makes the job ``PERMANENT`` and sends the question to a
    human, rather than backing off and retrying forever."""
    chain = FallbackAIProvider(
        [
            _StubProvider("first", SchemaViolation("bad")),
            _StubProvider("second", SchemaViolation("bad")),
        ]
    )

    with pytest.raises(SchemaViolation):
        chain.grade(_VALID_REQUEST)


def test_describe_follows_the_last_attempted_child() -> None:
    """So a failure record made after an exhausted chain names the provider
    whose exception the caller actually received -- not one never reached."""
    chain = FallbackAIProvider(
        [
            _StubProvider("first", ProviderServerError()),
            _StubProvider("second", ProviderServerError()),
        ]
    )

    assert chain.describe().provider == "first"  # before any call: the next to be tried
    with pytest.raises(ProviderServerError):
        chain.grade(_VALID_REQUEST)
    assert chain.describe().provider == "second"


def test_an_exhausted_chain_records_every_link_it_tried() -> None:
    """Issue #97 review round 4: the last link's failure alone cannot say
    that Vertex was 403 *before* OpenRouter was 401 -- and after the request
    URL stopped being logged (`api.sidecar._VERBOSE_LOGGERS`) nothing else
    said it either. Every attempt is recorded, in the order tried."""
    chain = FallbackAIProvider(
        [
            _StubProvider("gemini", ProviderUnavailable("forbidden", status_code=403)),
            _StubProvider("openrouter", ProviderUnavailable("unauthorized", status_code=401)),
        ]
    )

    with pytest.raises(ProviderUnavailable) as raised:
        chain.grade(_VALID_REQUEST)

    assert raised.value.attempts == (
        ProviderAttempt(provider="gemini", error="ProviderUnavailable", status_code=403),
        ProviderAttempt(provider="openrouter", error="ProviderUnavailable", status_code=401),
    )


def test_a_link_with_no_http_response_records_no_status() -> None:
    """A timeout or a transport error has no status number, and one is not
    invented -- ``None`` says "there was no response" rather than implying
    some code was seen."""
    chain = FallbackAIProvider([_StubProvider("openai", ProviderTimeoutError("timed out"))])

    with pytest.raises(ProviderTimeoutError) as raised:
        chain.grade(_VALID_REQUEST)

    assert raised.value.attempts == (
        ProviderAttempt(provider="openai", error="ProviderTimeoutError", status_code=None),
    )


def test_a_fall_through_is_logged_even_when_the_chain_then_succeeds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Otherwise "Vertex has been 403ing all afternoon and every grade came
    from OpenAI" is invisible: the caller is handed a perfectly good grade
    and no exception is ever raised."""
    chain = FallbackAIProvider(
        [
            _StubProvider("gemini", ProviderUnavailable("forbidden", status_code=403)),
            _StubProvider("openai"),
        ]
    )

    with caplog.at_level(logging.WARNING):
        chain.grade(_VALID_REQUEST)

    assert "gemini ProviderUnavailable status=403" in caplog.text


def test_the_logged_attempt_never_carries_the_exception_message() -> None:
    """The same rule as everywhere else in Issue #97: what is published is
    assembled from a literal provider id, an exception class name and a
    number -- never filtered out of text this layer does not control."""
    message = "forbidden for project sk-secret-pasted-DO-NOT-USE"
    chain = FallbackAIProvider(
        [_StubProvider("gemini", ProviderUnavailable(message, status_code=403))]
    )

    with pytest.raises(ProviderUnavailable) as raised:
        chain.grade(_VALID_REQUEST)

    assert str(raised.value.attempts[0]) == "gemini ProviderUnavailable status=403"
    assert "sk-secret-pasted-DO-NOT-USE" not in str(raised.value.attempts[0])


def test_an_empty_chain_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="at least one provider"):
        FallbackAIProvider([])


def test_an_exception_outside_the_port_contract_is_not_swallowed() -> None:
    """Deliberate, and the counterpart to each adapter's malformed-envelope
    tests: the chain falls through on exactly the two exceptions the
    ``AIProvider`` port declares, and an adapter raising anything else is a
    bug that must stay visible.

    Routing around it would mean the same malformed body trips the same
    adapter on every request while the chain quietly runs on the
    second-choice model, reporting nothing. The fix belongs in the adapter,
    which is why the three chain-stopping failures found in review were all
    fixed there rather than here (code review finding)."""
    first = _StubProvider("first", AttributeError("'NoneType' object has no attribute 'get'"))
    second = _StubProvider("second")

    with pytest.raises(AttributeError):
        FallbackAIProvider([first, second]).grade(_VALID_REQUEST)
    assert second.calls == 0
