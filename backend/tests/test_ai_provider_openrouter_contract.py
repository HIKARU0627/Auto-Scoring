"""Contract tests for :class:`OpenRouterAIProvider` (Issue #44).

Exercises ``AIProviderContract`` against a fake OpenRouter HTTP transport
(``httpx.MockTransport``) -- never calls the real OpenRouter API. A real
call is a separate, explicit live probe (``docs/poc-2-ai-grading.md``
section 7.3), never part of this offline suite.
"""

import json

import httpx
import pytest

from auto_scoring.adapters.ai_grading.openrouter_provider import OpenRouterAIProvider
from auto_scoring.domain.ai_provider import AIProvider, ProviderUnavailable

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
        "choices": [{"message": {"role": "assistant", "content": content}}],
    }


def _fake_transport_handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    user_text = payload["messages"][0]["content"][0]["text"]
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


def test_descriptor_records_the_routed_model_as_version() -> None:
    """OpenRouter can silently route a model id to a different underlying
    deployment; recording the echoed ``model`` as ``version`` keeps the
    reproducibility descriptor (Issue #14 "再現条件") honest about which
    deployment actually answered."""
    provider = _make_provider()
    response = provider.grade(_VALID_REQUEST)
    assert response.descriptor.version == "openrouter-routed/echo"
