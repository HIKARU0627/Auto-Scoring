"""Contract tests for :class:`CodexAppServerProvider` (Issue #44).

Exercises ``AIProviderContract`` against a fake in-memory JSON-RPC transport
-- never spawns a real ``codex`` process and never requires a live Codex
login/subscription. A real end-to-end call against ``codex app-server`` is a
separate, explicit live probe (``docs/poc-2-ai-grading.md`` section 7.3),
never part of this offline suite.
"""

import json
import os
from collections.abc import Callable

import pytest

from auto_scoring.adapters.ai_grading.codex_app_server_provider import CodexAppServerProvider
from auto_scoring.domain.ai_provider import AIProvider, ProviderUnavailable, SchemaViolation

from .test_ai_provider_contract import _VALID_REQUEST, AIProviderContract

_OCR_TEXT = "答案テキスト"
_QUESTION_ID_MARKER = 'The questionId in your response must be exactly "'


def _canned_grading_json(question_id: str) -> str:
    if question_id == "malformed":
        return json.dumps({"questionId": question_id, "grading": {"score": 1}})
    return json.dumps(
        {
            "questionId": question_id,
            "recognition": {"text": _OCR_TEXT, "confidence": 0.9},
            "grading": {"score": 4, "maxScore": 5, "confidence": 0.8},
            "criteria": [{"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "根拠"}],
            "comment": "コメント",
            "rationale": "根拠",
            "annotations": [],
        }
    )


class _FakeAppServerTransport:
    """Replays a canned ``turn/completed`` notification instead of speaking
    to a real ``codex app-server`` subprocess. Test-only scaffolding, mirrors
    ``test_ai_provider_contract._ReplayAIProvider``."""

    def __init__(self) -> None:
        self._thread_id = "thread-1"
        self._last_question_id: str | None = None
        self.closed = False

    def request(
        self, method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        if method == "initialize":
            return {}
        if method == "thread/start":
            assert params["sandbox"] == "read-only"
            assert params["approvalPolicy"] == "never"
            return {"thread": {"id": self._thread_id}}
        if method == "turn/start":
            assert params["threadId"] == self._thread_id
            assert "outputSchema" in params
            input_items = params["input"]
            assert isinstance(input_items, list)
            text = input_items[0]["text"]
            start = text.index(_QUESTION_ID_MARKER) + len(_QUESTION_ID_MARKER)
            end = text.index('"', start)
            self._last_question_id = text[start:end]
            image_path = input_items[1]["path"]
            assert input_items[1]["type"] == "localImage"
            assert os.path.exists(image_path)  # the adapter must write the image to disk
            return {}
        raise AssertionError(f"unexpected method: {method}")

    def wait_for_notification(
        self,
        method: str,
        matches: Callable[[dict[str, object]], bool],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        assert method == "turn/completed"
        assert self._last_question_id is not None
        params: dict[str, object] = {
            "threadId": self._thread_id,
            "turn": {
                "id": "turn-1",
                "status": "completed",
                "items": [
                    {
                        "id": "item-1",
                        "type": "agentMessage",
                        "text": _canned_grading_json(self._last_question_id),
                    }
                ],
            },
        }
        assert matches(params)
        return params

    def close(self) -> None:
        self.closed = True


def _make_provider() -> CodexAppServerProvider:
    return CodexAppServerProvider(prompt_version="v1", transport=_FakeAppServerTransport())


class TestCodexAppServerProviderContract(AIProviderContract):
    @pytest.fixture
    def provider(self) -> AIProvider:
        return _make_provider()


def test_grade_cleans_up_the_temporary_image_file() -> None:
    """The cropped answer image (potentially student handwriting) must not
    linger on disk after the turn completes (AGENTS.md "Security")."""
    transport = _FakeAppServerTransport()
    provider = CodexAppServerProvider(prompt_version="v1", transport=transport)

    written_paths: list[str] = []
    original_request = transport.request

    def _spying_request(
        method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        if method == "turn/start":
            written_paths.append(params["input"][1]["path"])  # type: ignore[index]
        return original_request(method, params, timeout_seconds=timeout_seconds)

    transport.request = _spying_request  # type: ignore[method-assign]
    provider.grade(_VALID_REQUEST)

    assert written_paths
    assert not os.path.exists(written_paths[0])


def test_schema_violation_when_turn_produces_no_agent_message() -> None:
    class _NoAgentMessageTransport(_FakeAppServerTransport):
        def wait_for_notification(
            self,
            method: str,
            matches: Callable[[dict[str, object]], bool],
            *,
            timeout_seconds: float,
        ) -> dict[str, object]:
            params: dict[str, object] = {
                "threadId": self._thread_id,
                "turn": {"id": "turn-1", "status": "completed", "items": []},
            }
            assert matches(params)
            return params

    provider = CodexAppServerProvider(prompt_version="v1", transport=_NoAgentMessageTransport())
    with pytest.raises(SchemaViolation):
        provider.grade(_VALID_REQUEST)


def test_provider_unavailable_when_turn_fails() -> None:
    class _FailedTurnTransport(_FakeAppServerTransport):
        def wait_for_notification(
            self,
            method: str,
            matches: Callable[[dict[str, object]], bool],
            *,
            timeout_seconds: float,
        ) -> dict[str, object]:
            params: dict[str, object] = {
                "threadId": self._thread_id,
                "turn": {"id": "turn-1", "status": "failed", "items": []},
            }
            assert matches(params)
            return params

    provider = CodexAppServerProvider(prompt_version="v1", transport=_FailedTurnTransport())
    with pytest.raises(ProviderUnavailable):
        provider.grade(_VALID_REQUEST)


def test_provider_unavailable_on_notification_timeout() -> None:
    class _TimingOutTransport(_FakeAppServerTransport):
        def wait_for_notification(
            self,
            method: str,
            matches: Callable[[dict[str, object]], bool],
            *,
            timeout_seconds: float,
        ) -> dict[str, object]:
            raise TimeoutError

    provider = CodexAppServerProvider(prompt_version="v1", transport=_TimingOutTransport())
    with pytest.raises(ProviderUnavailable):
        provider.grade(_VALID_REQUEST)
