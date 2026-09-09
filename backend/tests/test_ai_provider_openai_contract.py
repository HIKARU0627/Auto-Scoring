"""Contract tests for :class:`OpenAIAIProvider` (Issue #35).

Deliberately short: the whole Chat Completions call path is shared with the
OpenRouter adapter (``_openai_chat.ChatCompletionsAIProvider``) and is
covered once, in ``test_ai_provider_openrouter_contract.py`` -- duplicating
those cases here would only pin the same code twice. What is tested here is
what is *specific* to calling OpenAI directly: its own base URL, its own
retention opt-out, and the absence of OpenRouter's routing preference (which
OpenAI would reject as an unknown parameter).

Never calls the real OpenAI API: a fake transport (``httpx.MockTransport``)
answers every request. A real call is a separate, explicit live probe
(``docs/poc-2-ai-grading.md`` section 7.4).
"""

import json

import httpx
import pytest

from auto_scoring.adapters.ai_grading.openai_provider import OpenAIAIProvider
from auto_scoring.domain.ai_provider import AIProvider

from .test_ai_provider_contract import (
    _VALID_REQUEST,
    MALFORMED_MARKER,
    AIProviderContract,
)

_CAPTURED: list[dict[str, object]] = []


def _canned_chat_completion(*, malformed: bool) -> dict[str, object]:
    if malformed:
        content = json.dumps({"grading": {"score": 1}})
    else:
        content = json.dumps(
            {
                "recognition": {"text": "答案テキスト", "confidence": 0.9},
                "grading": {"score": 4, "maxScore": 5, "confidence": 0.8},
                "criteria": [
                    {"index": 1, "result": "pass", "confidence": 0.9, "rationale": "根拠"}
                ],
                "comment": "コメント",
                "rationale": "根拠",
                "annotations": [],
            }
        )
    # OpenAI echoes the dated snapshot it actually ran, which is what ends
    # up in ProviderDescriptor.version.
    return {
        "model": "gpt-4o-mini-2024-07-18",
        "choices": [{"message": {"role": "assistant", "content": content}}],
    }


def _handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    _CAPTURED.append({"url": str(request.url), "payload": payload})
    user_text = payload["messages"][1]["content"][0]["text"]
    # Selected from the prompt text itself: since Issue #117 nothing that
    # identifies the question is sent, so a request asking for the malformed
    # canned response says so in the one field this fake can still see.
    return httpx.Response(
        200, json=_canned_chat_completion(malformed=MALFORMED_MARKER in user_text)
    )


def _make_provider() -> OpenAIAIProvider:
    return OpenAIAIProvider(
        api_key="test-key",
        model="gpt-4o-mini",
        prompt_version="v1",
        client=httpx.Client(
            transport=httpx.MockTransport(_handler), base_url="https://api.openai.test/v1"
        ),
    )


class TestOpenAIAIProviderContract(AIProviderContract):
    @pytest.fixture
    def provider(self) -> AIProvider:
        return _make_provider()


def test_declares_its_own_provider_id() -> None:
    """``openai`` is one of ``report.py``'s canonical candidate ids and the
    value that reaches ``GradeResult.provider``; it must not inherit the
    base class's placeholder name."""
    assert _make_provider().describe().provider == "openai"


def test_opts_out_of_response_storage_and_sends_no_openrouter_routing() -> None:
    """``store: false`` is the per-request retention opt-out (decision
    record section 6.6). OpenRouter's ``provider`` routing preference must
    *not* be sent: OpenAI rejects unknown parameters, so leaking it here
    would fail every call."""
    _CAPTURED.clear()
    _make_provider().grade(_VALID_REQUEST)

    payload = _CAPTURED[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["store"] is False
    assert "provider" not in payload
    assert str(_CAPTURED[0]["url"]).endswith("/chat/completions")


def test_records_the_dated_snapshot_as_the_descriptor_version() -> None:
    """Issue #14 "再現条件": ``gpt-4o-mini`` resolves to a dated snapshot,
    and two calls that ran against different snapshots are two different
    configurations."""
    response = _make_provider().grade(_VALID_REQUEST)
    assert response.descriptor.version is not None
    assert json.loads(response.descriptor.version) == {"model": "gpt-4o-mini-2024-07-18"}
