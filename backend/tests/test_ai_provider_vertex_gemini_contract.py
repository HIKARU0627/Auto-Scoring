"""Contract tests for :class:`VertexGeminiAIProvider` (Issue #35).

Exercises ``AIProviderContract`` against a fake Vertex AI HTTP transport
(``httpx.MockTransport``) and fake ADC credentials -- never calls the real
Vertex AI API and never touches the developer's ``gcloud`` login. A real
call is a separate, explicit live probe (``docs/poc-2-ai-grading.md``
section 7.4), never part of this offline suite.
"""

import json

import httpx
import pytest
from google.auth.credentials import Credentials

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading.vertex_gemini_provider import VertexGeminiAIProvider
from auto_scoring.domain.ai_provider import (
    AIProvider,
    ProviderRateLimitedError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailable,
    SchemaViolation,
)

from .test_ai_provider_contract import _VALID_REQUEST, AIProviderContract

_OCR_TEXT = "答案テキスト"
_PROJECT = "test-project"


class _FakeCredentials(Credentials):
    """ADC credentials that are always valid and never hit the network."""

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.token = "fake-access-token"

    def refresh(self, request: object) -> None:
        self.token = "fake-access-token"


def _tokens() -> AdcTokenSource:
    return AdcTokenSource(credentials=_FakeCredentials(), project_id=_PROJECT)


def _canned_generate_content(question_id: str) -> dict[str, object]:
    if question_id == "malformed":
        content = json.dumps({"questionId": question_id, "grading": {"score": 1}})
    else:
        content = json.dumps(
            {
                "questionId": question_id,
                "recognition": {"text": _OCR_TEXT, "confidence": 0.9},
                "grading": {"score": 4, "maxScore": 5, "confidence": 0.8},
                "criteria": [
                    {"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "根拠"}
                ],
                "comment": "コメント",
                "rationale": "根拠",
                "annotations": [],
            }
        )
    return {
        "modelVersion": "gemini-2.5-flash-001",
        "candidates": [{"content": {"role": "model", "parts": [{"text": content}]}}],
    }


def _fake_transport_handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    assert request.headers["Authorization"] == "Bearer fake-access-token"
    # The fixed rules travel on Vertex's own instruction channel, never
    # mixed into the user turn that carries student-controlled OCR text.
    assert payload["systemInstruction"]["parts"][0]["text"]
    user_text = payload["contents"][0]["parts"][0]["text"]
    marker = 'The questionId in your response must be exactly "'
    start = user_text.index(marker) + len(marker)
    end = user_text.index('"', start)
    return httpx.Response(200, json=_canned_generate_content(user_text[start:end]))


def _make_provider(handler: object = None, *, location: str = "global") -> VertexGeminiAIProvider:
    client = httpx.Client(
        transport=httpx.MockTransport(handler or _fake_transport_handler)  # type: ignore[arg-type]
    )
    return VertexGeminiAIProvider(
        model="gemini-2.5-flash",
        prompt_version="v1",
        tokens=_tokens(),
        location=location,
        client=client,
    )


class TestVertexGeminiAIProviderContract(AIProviderContract):
    @pytest.fixture
    def provider(self) -> AIProvider:
        return _make_provider()


def test_endpoint_uses_the_global_host_without_a_region_prefix() -> None:
    """`global` has its own hostname; every regional location prefixes it.
    Getting this wrong is a 404 on every call, so it is pinned here."""
    seen: list[str] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return _fake_transport_handler(request)

    _make_provider(_capture).grade(_VALID_REQUEST)
    _make_provider(_capture, location="asia-northeast1").grade(_VALID_REQUEST)

    assert seen[0].startswith(
        f"https://aiplatform.googleapis.com/v1/projects/{_PROJECT}/locations/global/"
    )
    assert seen[1].startswith(
        "https://asia-northeast1-aiplatform.googleapis.com/v1/projects/"
        f"{_PROJECT}/locations/asia-northeast1/"
    )


def test_records_the_answering_deployment_as_the_descriptor_version() -> None:
    """Issue #14 "再現条件": two calls that ran against different Gemini
    deployments must not share a reproducibility bucket, so the
    ``modelVersion`` Vertex reports is kept, not just the requested alias."""
    provider = _make_provider()
    response = provider.grade(_VALID_REQUEST)
    assert response.descriptor.version == "gemini-2.5-flash-001"
    assert provider.describe().version == "gemini-2.5-flash-001"


def test_a_failed_call_does_not_keep_the_previous_deployment() -> None:
    """A call that never reached Vertex must not be attributed to the
    upstream the *previous* call happened to reach (code review finding)."""
    remaining_successes = [_fake_transport_handler]

    def _then_fail(request: httpx.Request) -> httpx.Response:
        if remaining_successes:
            return remaining_successes.pop()(request)
        return httpx.Response(503)

    provider = _make_provider(_then_fail)
    provider.grade(_VALID_REQUEST)
    with pytest.raises(ProviderServerError):
        provider.grade(_VALID_REQUEST)
    assert provider.describe().version is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, ProviderRateLimitedError),
        (500, ProviderServerError),
        (503, ProviderServerError),
        (401, ProviderUnavailable),
    ],
)
def test_http_failures_are_classified(status: int, expected: type[Exception]) -> None:
    """docs/ai-grading-pipeline.md keys both the fallback decision and the
    queue's ``ErrorCategory`` on these specific types."""
    provider = _make_provider(lambda request: httpx.Response(status, json={"error": "x"}))
    with pytest.raises(expected):
        provider.grade(_VALID_REQUEST)


def test_timeout_is_classified_as_a_timeout() -> None:
    def _timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(ProviderTimeoutError):
        _make_provider(_timeout).grade(_VALID_REQUEST)


def test_a_blocked_or_empty_candidate_is_a_schema_violation() -> None:
    """A safety block or a truncated candidate is a response the caller must
    route to needs-review -- not a transport failure the queue would retry."""
    provider = _make_provider(
        lambda request: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})
    )
    with pytest.raises(SchemaViolation):
        provider.grade(_VALID_REQUEST)


def test_multi_part_text_is_concatenated_in_order() -> None:
    """Gemini may split one JSON document across several text parts; reading
    only the first would truncate it into invalid JSON and report a schema
    violation the model never actually committed."""
    body = json.dumps(
        {
            "questionId": "q1",
            "recognition": {"text": _OCR_TEXT, "confidence": 0.9},
            "grading": {"score": 4, "maxScore": 5, "confidence": 0.8},
            "criteria": [{"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "根拠"}],
            "comment": "コメント",
            "rationale": "根拠",
            "annotations": [],
        }
    )
    split = len(body) // 2
    provider = _make_provider(
        lambda request: httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": body[:split]}, {"text": body[split:]}]}}
                ]
            },
        )
    )
    assert provider.grade(_VALID_REQUEST).score == 4


def test_no_project_id_is_a_credentials_error_not_a_silent_default() -> None:
    """Guessing a project would send a real answer crop to the wrong Google
    Cloud project."""
    with pytest.raises(AdcCredentialsError):
        AdcTokenSource(credentials=_FakeCredentials(), project_id="   ")


# --- the port's exception contract: nothing else may escape grade() ---


def test_an_adc_failure_is_a_provider_unavailable_not_a_chain_stopper() -> None:
    """An expired refresh token, or a token endpoint that is down, must be
    a `ProviderUnavailable` so `FallbackAIProvider` moves on to Codex /
    OpenRouter / OpenAI (code review finding: `AdcCredentialsError` was
    raised from inside `grade()`'s try block but matched by none of its
    handlers, so it escaped the port's contract and stopped the chain).

    The message carries the exception type only -- never token material.
    """

    class _ExpiredTokens(AdcTokenSource):
        def bearer_token(self) -> str:
            raise AdcCredentialsError("refresh failed")

    provider = VertexGeminiAIProvider(
        model="gemini-2.5-flash",
        prompt_version="v1",
        tokens=_ExpiredTokens(credentials=_FakeCredentials(), project_id=_PROJECT),
        client=httpx.Client(transport=httpx.MockTransport(_fake_transport_handler)),
    )

    with pytest.raises(ProviderUnavailable) as raised:
        provider.grade(_VALID_REQUEST)
    assert "refresh failed" not in str(raised.value)


@pytest.mark.parametrize(
    "body",
    [
        {"candidates": [{"content": {"parts": [None]}}]},
        {"candidates": [{"content": {"parts": ["a bare string"]}}]},
        {"candidates": [{"content": {"parts": {"text": "not a list"}}}]},
        {"candidates": [{"content": {"parts": [{"text": 42}]}}]},
        {"candidates": [{"content": {}}]},
        {"candidates": []},
        {"candidates": "not a list"},
    ],
)
def test_a_malformed_2xx_envelope_is_a_schema_violation(body: dict[str, object]) -> None:
    """Every shape here is a *response*, so it belongs on the needs-review
    path -- and, just as importantly, it must arrive as one of the two
    exceptions this port declares. `{"parts": [null]}` used to reach
    `part.get()` and raise an uncaught AttributeError, which the fallback
    chain does not catch, so a single malformed body from Gemini stopped
    the whole chain instead of falling through to the next provider (code
    review finding)."""
    provider = _make_provider(lambda request: httpx.Response(200, json=body))

    with pytest.raises(SchemaViolation):
        provider.grade(_VALID_REQUEST)


def test_a_corrupt_compressed_body_does_not_stop_the_chain() -> None:
    """`httpx.DecodingError` descends from `RequestError`, not from
    `TransportError`, so an adapter catching the interesting subclasses by
    name let it straight through -- outside the port's exception contract,
    which means `FallbackAIProvider` stopped instead of trying the next
    provider (code review finding). Adapters catch `httpx.HTTPError` now,
    which is httpx's own root for everything a request can raise."""

    def _corrupt_gzip(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"this is not gzip at all", headers={"content-encoding": "gzip"}
        )

    with pytest.raises(ProviderUnavailable):
        _make_provider(_corrupt_gzip).grade(_VALID_REQUEST)
