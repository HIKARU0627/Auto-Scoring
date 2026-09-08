"""Contract tests for :class:`OpenRouterAIProvider` (Issue #44).

Exercises ``AIProviderContract`` against a fake OpenRouter HTTP transport
(``httpx.MockTransport``) -- never calls the real OpenRouter API. A real
call is a separate, explicit live probe (``docs/poc-2-ai-grading.md``
section 7.3), never part of this offline suite.
"""

import json

import httpx
import pytest

from auto_scoring.adapters.ai_grading._prompt import GRADING_SYSTEM_INSTRUCTIONS
from auto_scoring.adapters.ai_grading.openrouter_provider import OpenRouterAIProvider
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


def _canned_chat_completion(question_id: str) -> dict[str, object]:
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
        "model": "openrouter-routed/echo",
        "provider": "some-upstream-vendor",
        "choices": [{"message": {"role": "assistant", "content": content}}],
    }


def _fake_transport_handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    assert payload["messages"][0]["role"] == "system"
    user_text = payload["messages"][1]["content"][0]["text"]
    marker = 'The questionId in your response must be exactly "'
    start = user_text.index(marker) + len(marker)
    end = user_text.index('"', start)
    question_id = user_text[start:end]
    return httpx.Response(200, json=_canned_chat_completion(question_id))


def _make_client() -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(_fake_transport_handler),
        base_url="https://openrouter.test/api/v1",
    )


def _make_provider(client: httpx.Client | None = None) -> OpenRouterAIProvider:
    return OpenRouterAIProvider(
        api_key="test-key",
        model="test/model",
        prompt_version="v1",
        client=client or _make_client(),
    )


class TestOpenRouterAIProviderContract(AIProviderContract):
    @pytest.fixture
    def provider(self) -> AIProvider:
        return _make_provider()


def test_provider_unavailable_on_transport_error() -> None:
    def _raise_transport_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(_raise_transport_error),
        base_url="https://openrouter.test/api/v1",
    )
    provider = _make_provider(client)

    with pytest.raises(ProviderUnavailable):
        provider.grade(_VALID_REQUEST)


def test_provider_unavailable_on_http_error_status() -> None:
    def _rate_limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    client = httpx.Client(
        transport=httpx.MockTransport(_rate_limited),
        base_url="https://openrouter.test/api/v1",
    )
    provider = _make_provider(client)

    with pytest.raises(ProviderUnavailable):
        provider.grade(_VALID_REQUEST)


def test_provider_unavailable_on_non_json_response_body() -> None:
    """A 200 response with a non-JSON body (an outage page, a misbehaving
    proxy, ...) must convert to ProviderUnavailable, not leak a raw
    json.JSONDecodeError past this port's exception contract (code review
    finding)."""

    def _html_error_page(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not json</html>")

    client = httpx.Client(
        transport=httpx.MockTransport(_html_error_page),
        base_url="https://openrouter.test/api/v1",
    )
    provider = _make_provider(client)

    with pytest.raises(ProviderUnavailable):
        provider.grade(_VALID_REQUEST)


def test_provider_unavailable_on_invalid_utf8_response_body() -> None:
    """A body containing invalid UTF-8 fails even earlier than JSON
    parsing -- as a ``UnicodeDecodeError`` from ``httpx.Response.json()``'s
    internal text decoding -- and must be normalized the same way as any
    other malformed transport response, never left to escape as an
    unclassified exception with the raw response bytes in its traceback
    (code review finding)."""

    def _invalid_utf8_body(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"\xff\xfe\x00not valid utf-8 \xfe\xff",
            headers={"content-type": "application/json; charset=utf-8"},
        )

    client = httpx.Client(
        transport=httpx.MockTransport(_invalid_utf8_body),
        base_url="https://openrouter.test/api/v1",
    )
    provider = _make_provider(client)

    with pytest.raises(ProviderUnavailable):
        provider.grade(_VALID_REQUEST)


def test_descriptor_records_the_routed_model_and_upstream_provider_as_version() -> None:
    """OpenRouter can route the same model slug through different upstream
    providers; recording only ``model`` would pool calls that actually ran
    against different deployments into the same reproducibility bucket
    (code review finding). ``version`` must carry both the echoed ``model``
    and the top-level ``provider`` fingerprint."""
    provider = _make_provider()
    response = provider.grade(_VALID_REQUEST)
    assert response.descriptor.version is not None
    assert json.loads(response.descriptor.version) == {
        "model": "openrouter-routed/echo",
        "provider": "some-upstream-vendor",
    }


def test_provider_unavailable_includes_the_http_status_code() -> None:
    """Callers need the numeric status to apply the documented 429 backoff
    and tell a persistent auth/config failure (4xx) apart from a transient
    server error (5xx) (code review finding)."""

    def _rate_limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    client = httpx.Client(
        transport=httpx.MockTransport(_rate_limited),
        base_url="https://openrouter.test/api/v1",
    )
    provider = _make_provider(client)

    with pytest.raises(ProviderUnavailable, match="429"):
        provider.grade(_VALID_REQUEST)


def test_schema_violation_when_response_has_no_completion_message() -> None:
    """A 2xx response with valid JSON but a missing/malformed completion
    envelope (a refusal, a changed response shape, ...) is a malformed
    structured response, not a transport failure -- it must route to
    SchemaViolation (needs-review), not ProviderUnavailable (retry/
    unavailable-rate) (code review finding)."""

    def _no_choices(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "x", "choices": []})

    client = httpx.Client(
        transport=httpx.MockTransport(_no_choices),
        base_url="https://openrouter.test/api/v1",
    )
    provider = _make_provider(client)

    with pytest.raises(SchemaViolation):
        provider.grade(_VALID_REQUEST)


def test_describe_reflects_the_route_of_a_schema_violating_call() -> None:
    """The route fingerprint must be captured before the completion's
    structure/content is validated at all, so a schema-violating call is
    still attributable to the correct model/upstream-provider bucket
    instead of leaving `describe().version` as None (code review finding:
    otherwise a route's own schema_violation_rate would be understated by
    every failure silently falling into an unattributed bucket)."""

    def _malformed_but_valid_envelope(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "openrouter-routed/echo",
                "provider": "some-upstream-vendor",
                "choices": [{"message": {"role": "assistant", "content": "not json"}}],
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(_malformed_but_valid_envelope),
        base_url="https://openrouter.test/api/v1",
    )
    provider = _make_provider(client)

    with pytest.raises(SchemaViolation):
        provider.grade(_VALID_REQUEST)

    assert provider.describe().version is not None
    assert json.loads(provider.describe().version) == {  # type: ignore[arg-type]
        "model": "openrouter-routed/echo",
        "provider": "some-upstream-vendor",
    }


def test_grading_instructions_go_through_the_system_message() -> None:
    """Fixed grading rules must be sent over the trusted `system` channel,
    not mixed into the same user-level message as the student-controlled
    OCR text (code review finding: a JSON Schema alone only constrains
    response shape, not whether an injected instruction inside the OCR text
    changes the awarded score)."""
    captured: dict[str, object] = {}

    def _capturing_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured["messages"] = payload["messages"]
        return _fake_transport_handler(request)

    client = httpx.Client(
        transport=httpx.MockTransport(_capturing_handler),
        base_url="https://openrouter.test/api/v1",
    )
    provider = _make_provider(client)
    provider.grade(_VALID_REQUEST)

    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0] == {"role": "system", "content": GRADING_SYSTEM_INSTRUCTIONS}
    user_text = messages[1]["content"][0]["text"]
    assert "UNTRUSTED STUDENT OCR" in user_text


def test_grade_requests_zero_data_retention() -> None:
    """A real answer-image crop must not reach an upstream that may retain
    or train on it just because the caller's OpenRouter account itself
    hasn't been switched to a global zero-data-retention setting -- this
    request-level preference must be sent on every call (code review
    finding; decision record's opt-out/ZDR requirement).

    Both ``data_collection: "deny"`` and ``zdr: True`` are required
    (code review finding): ``data_collection: "deny"`` alone only
    restricts routing to providers whose training/data-collection policy
    is "deny" -- a provider can still retain input for other purposes
    (e.g. abuse monitoring) under that policy. ``zdr: True`` is
    OpenRouter's separate, stricter constraint that actually enforces
    zero data retention."""
    captured: dict[str, object] = {}

    def _capturing_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured["provider"] = payload.get("provider")
        return _fake_transport_handler(request)

    client = httpx.Client(
        transport=httpx.MockTransport(_capturing_handler),
        base_url="https://openrouter.test/api/v1",
    )
    provider = _make_provider(client)
    provider.grade(_VALID_REQUEST)

    assert captured["provider"] == {"data_collection": "deny", "zdr": True}


def test_schema_violation_when_response_body_is_not_a_json_object() -> None:
    """A 2xx response whose top-level JSON value isn't even an object (a
    bare array, in this case) must not let `_routing_fingerprint`'s
    `.get(...)` calls raise an uncaught AttributeError -- it is a malformed
    structured response, routed to SchemaViolation like any other broken
    envelope shape (code review finding)."""

    def _json_array_body(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    client = httpx.Client(
        transport=httpx.MockTransport(_json_array_body),
        base_url="https://openrouter.test/api/v1",
    )
    provider = _make_provider(client)

    with pytest.raises(SchemaViolation):
        provider.grade(_VALID_REQUEST)


def test_describe_does_not_report_a_stale_route_after_a_later_failure() -> None:
    """Once a successful call has set `_last_route`, a later failed
    attempt (here: a 429) must not leave `describe()` still reporting the
    *previous* call's route -- that would misattribute this attempt's
    unavailability to an upstream it never actually reached (code review
    finding)."""
    call_count = {"value": 0}

    def _succeed_then_rate_limit(request: httpx.Request) -> httpx.Response:
        call_count["value"] += 1
        if call_count["value"] == 1:
            return _fake_transport_handler(request)
        return httpx.Response(429, json={"error": "rate limited"})

    client = httpx.Client(
        transport=httpx.MockTransport(_succeed_then_rate_limit),
        base_url="https://openrouter.test/api/v1",
    )
    provider = _make_provider(client)

    provider.grade(_VALID_REQUEST)
    assert provider.describe().version is not None

    with pytest.raises(ProviderUnavailable):
        provider.grade(_VALID_REQUEST)

    assert provider.describe().version is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, ProviderRateLimitedError),
        (500, ProviderServerError),
        (502, ProviderServerError),
        (401, ProviderUnavailable),
    ],
)
def test_http_failures_are_classified_for_the_fallback_chain(
    status: int, expected: type[Exception]
) -> None:
    """Issue #35: the fallback chain and the queue's ``ErrorCategory`` both
    key on the *specific* exception type (docs/ai-grading-pipeline.md
    "どの失敗で次へ落とすか"). Raising a bare ``ProviderUnavailable`` for a
    429 -- what this adapter did before ``_http`` existed -- forced
    ``GradingJobProcessor`` into ``ErrorCategory.UNKNOWN`` for a failure it
    could classify exactly. A plain 4xx stays bare: it is an auth/config
    problem the queue must not treat as a retryable rate limit."""
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json={"error": "x"})),
        base_url="https://openrouter.test/api/v1",
    )

    with pytest.raises(expected):
        _make_provider(client).grade(_VALID_REQUEST)


def test_timeout_is_classified_as_a_timeout() -> None:
    def _timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(_timeout), base_url="https://openrouter.test/api/v1"
    )

    with pytest.raises(ProviderTimeoutError):
        _make_provider(client).grade(_VALID_REQUEST)


@pytest.mark.parametrize(
    "body",
    [
        {"choices": [None]},
        {"choices": "not a list"},
        {"choices": {"0": {"message": {"content": "{}"}}}},
        {"choices": [{"message": None}]},
        {"choices": [{"message": {"content": 42}}]},
        {"choices": [{}]},
    ],
)
def test_a_malformed_2xx_envelope_is_a_schema_violation(body: dict[str, object]) -> None:
    """The shared Chat Completions path must turn any 2xx body into one of
    the two exceptions the ``AIProvider`` port declares. `FallbackAIProvider`
    falls through on exactly those, so an adapter leaking anything else
    stops the whole chain (code review finding; the same check exists for
    the Vertex AI adapter)."""
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
        base_url="https://openrouter.test/api/v1",
    )

    with pytest.raises(SchemaViolation):
        _make_provider(client).grade(_VALID_REQUEST)
