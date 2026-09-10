"""Contract tests for the `AnswerAreaDetector` adapters (Issue #105).

Both adapters are exercised against a fake HTTP transport
(``httpx.MockTransport``) and fake ADC credentials -- never the real Vertex AI
or OpenAI endpoints, and never the developer's ``gcloud`` login.

What these pin, beyond "a good response parses":

* a malformed response is a `SchemaViolation`, never a partial reading;
* **no exception ever carries the request or the response**. The pages are a
  cram school's copyrighted answer sheets and carry teacher names, school
  names, printed dates and a student's handwriting; an exception message is
  written to the sidecar's log, which outlives the session (AGENTS.md
  "Security");
* the page images actually reach the wire, and the question-number enum with
  them.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest
from google.auth.credentials import Credentials

from auto_scoring.adapters.ai.image_call import (
    ChatCompletionsImageCall,
    VertexGeminiImageCall,
)
from auto_scoring.adapters.ai_grading._google_adc import AdcTokenSource
from auto_scoring.adapters.answer_area_detection.detector import (
    SCHEMA_NAME,
    StructuredAnswerAreaDetector,
)
from auto_scoring.domain.ai_provider import (
    ProviderRateLimitedError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailable,
    SchemaViolation,
)
from auto_scoring.domain.answer_area_detection import (
    UNASSIGNED_QUESTION_LABEL,
    AnswerAreaDetectionRequest,
    AnswerAreaDetector,
)

#: Stands in for a rendered page. Never a real one -- these bytes only have to
#: be non-empty and sniff as PNG.
_PAGE = b"\x89PNG\r\n\x1a\nfake-page"

#: A phrase that must never appear in an exception. Placed in the *response*
#: body by the tests below, standing in for the material a real response would
#: quote back.
_SENSITIVE = "SENSITIVE-MATERIAL-MARKER"


def _request(*, pages: int = 1) -> AnswerAreaDetectionRequest:
    return AnswerAreaDetectionRequest(
        page_images=tuple(_PAGE for _ in range(pages)), question_numbers=("Q1", "Q2")
    )


def _valid_body() -> str:
    return json.dumps(
        {
            "areas": [
                {
                    "page": 1,
                    "question_number": "Q1",
                    "bbox": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4},
                    "note": None,
                }
            ]
        }
    )


class _FakeCredentials(Credentials):
    """ADC credentials that are always valid and never hit the network."""

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.token = "fake-access-token"

    def refresh(self, request: object) -> None:
        self.token = "fake-access-token"


def _vertex(handler: httpx.MockTransport) -> StructuredAnswerAreaDetector:
    return StructuredAnswerAreaDetector(
        VertexGeminiImageCall(
            model="gemini-test",
            tokens=AdcTokenSource(credentials=_FakeCredentials(), project_id="test-project"),
            temperature=0.0,
            timeout_seconds=1.0,
            client=httpx.Client(transport=handler),
        )
    )


def _chat(handler: httpx.MockTransport) -> StructuredAnswerAreaDetector:
    return StructuredAnswerAreaDetector(
        ChatCompletionsImageCall(
            provider="openai",
            api_key="fake-key",
            model="model-test",
            base_url="https://example.invalid/v1",
            label="OpenAI",
            schema_name=SCHEMA_NAME,
            extra_payload={"store": False},
            temperature=0.0,
            timeout_seconds=1.0,
            client=httpx.Client(transport=handler, base_url="https://example.invalid/v1"),
        )
    )


def _vertex_response(text: str) -> dict[str, Any]:
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}]}


def _chat_response(text: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": text}}]}


def _detector_for(kind: str, body_text: str) -> tuple[AnswerAreaDetector, list[dict[str, Any]]]:
    """One detector of each flavour, plus the list its sent payloads land in."""
    sent: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        envelope = _vertex_response(body_text) if kind == "vertex" else _chat_response(body_text)
        return httpx.Response(200, json=envelope)

    transport = httpx.MockTransport(handle)
    detector = _vertex(transport) if kind == "vertex" else _chat(transport)
    return detector, sent


@pytest.mark.parametrize("kind", ["vertex", "chat"])
class TestBothTransports:
    def test_parses_a_valid_response(self, kind: str) -> None:
        detector, _ = _detector_for(kind, _valid_body())
        output = detector.detect(_request())
        assert [area.question_number for area in output.areas] == ["Q1"]

    def test_sends_every_page_image(self, kind: str) -> None:
        detector, sent = _detector_for(kind, _valid_body())
        detector.detect(_request(pages=3))
        assert json.dumps(sent[0]).count(base64.b64encode(_PAGE).decode()) == 3

    def test_constrains_the_question_number_to_this_tests_questions(self, kind: str) -> None:
        """The attribution is a multiple-choice question on the wire too, not
        only in the local check (Issue #105 acceptance 3).
        """
        detector, sent = _detector_for(kind, _valid_body())
        detector.detect(_request())
        payload = json.dumps(sent[0], ensure_ascii=False)
        assert '"enum"' in payload
        assert UNASSIGNED_QUESTION_LABEL in payload

    def test_a_malformed_response_is_a_schema_violation(self, kind: str) -> None:
        detector, _ = _detector_for(kind, '{"areas": [{"page": 1}]}')
        with pytest.raises(SchemaViolation):
            detector.detect(_request())

    def test_a_response_outside_the_candidate_set_is_a_schema_violation(self, kind: str) -> None:
        body = json.dumps(
            {
                "areas": [
                    {
                        "page": 1,
                        "question_number": "Q9",
                        "bbox": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4},
                        "note": None,
                    }
                ]
            }
        )
        detector, _ = _detector_for(kind, body)
        with pytest.raises(SchemaViolation):
            detector.detect(_request())

    def test_a_non_json_body_is_a_schema_violation_not_a_partial_reading(self, kind: str) -> None:
        detector, _ = _detector_for(kind, "ここに回答欄があります")
        with pytest.raises(SchemaViolation):
            detector.detect(_request())

    def test_no_exception_carries_the_response_body(self, kind: str) -> None:
        """The one rule that matters most here. A provider that echoes the
        page content back into a malformed response must not put it into a log
        file that outlives the session.
        """
        detector, _ = _detector_for(kind, json.dumps({"areas": _SENSITIVE}))
        with pytest.raises(SchemaViolation) as caught:
            detector.detect(_request())
        assert _SENSITIVE not in str(caught.value)
        # `raise ... from None`: pydantic keeps the offending value in the
        # `ValidationError`'s `input_value`, and Python prints a chained
        # cause's own `str()`. Both `__cause__ is None` and
        # `__suppress_context__` are needed -- the context object still exists
        # (it is what was being handled), but neither `traceback` nor
        # `logging.exception` renders it once suppressed.
        assert caught.value.__cause__ is None
        assert caught.value.__suppress_context__ is True

    def test_a_2xx_body_that_is_not_an_object_is_a_schema_violation(self, kind: str) -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[1, 2, 3])

        transport = httpx.MockTransport(handle)
        detector = _vertex(transport) if kind == "vertex" else _chat(transport)
        with pytest.raises(SchemaViolation):
            detector.detect(_request())

    def test_a_2xx_body_with_no_completion_is_a_schema_violation(self, kind: str) -> None:
        """The call succeeded, so retrying reproduces it -- that is a
        malformed answer, not an unreachable provider.
        """

        def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": _SENSITIVE})

        transport = httpx.MockTransport(handle)
        detector = _vertex(transport) if kind == "vertex" else _chat(transport)
        with pytest.raises(SchemaViolation) as caught:
            detector.detect(_request())
        assert _SENSITIVE not in str(caught.value)

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (429, ProviderRateLimitedError),
            (503, ProviderServerError),
            (403, ProviderUnavailable),
        ],
    )
    def test_http_failures_are_classified(
        self, kind: str, status: int, expected: type[Exception]
    ) -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, text=_SENSITIVE)

        transport = httpx.MockTransport(handle)
        detector = _vertex(transport) if kind == "vertex" else _chat(transport)
        with pytest.raises(expected) as caught:
            detector.detect(_request())
        assert _SENSITIVE not in str(caught.value)

    def test_a_timeout_is_a_timeout(self, kind: str) -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        transport = httpx.MockTransport(handle)
        detector = _vertex(transport) if kind == "vertex" else _chat(transport)
        with pytest.raises(ProviderTimeoutError):
            detector.detect(_request())


def test_vertex_joins_several_text_parts() -> None:
    """Gemini may split one JSON document across parts; reading only the first
    would truncate it into invalid JSON and report a schema violation the
    model never committed.
    """
    body = _valid_body()
    split = len(body) // 2

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": body[:split]}, {"text": body[split:]}],
                        }
                    }
                ]
            },
        )

    assert _vertex(httpx.MockTransport(handle)).detect(_request()).areas
