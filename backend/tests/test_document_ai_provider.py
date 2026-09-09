"""`DocumentAiOCRProvider` against a mock transport (Issue #114).

No network, no credentials: `httpx.MockTransport` serves responses in
Document AI's own shape, so this runs in ordinary CI. The live-provider
probe is a separate, secret-bearing job (Issue #54).

Three things are pinned here that are not about "does it parse":

* **What is sent.** Design section 26.1.1 splits sending by purpose, and
  reading a student's answer is the "answer content" row: the payload is the
  answer-area crop only. A page image would carry the header (name, student
  id, cram-school and course name) on every question of every answer.
* **What is never said.** Nothing from the request or the response reaches an
  exception message -- not the recognized text, not the processor resource
  name, not the access token (PR #100's discipline).
* **How a failure is classified.** The queue's retry policy keys off the
  exception type (`domain.retry_policy`), so a 429 that came back as a
  generic error would be retried as a permanent misconfiguration or not at
  all.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from auto_scoring.adapters.ocr.document_ai_provider import DocumentAiOCRProvider
from auto_scoring.domain.ocr import (
    ConfidenceBand,
    OCRProviderError,
    OCRRateLimitedError,
    OCRResponseSchemaError,
    OCRServerError,
    OCRTimeoutError,
)
from tests.test_ocr_provider_contract import (
    PROCESSOR,
    document_ai_body,
    document_ai_provider,
    fake_tokens,
)

_CROP = b"\x89PNG\r\n\x1a\nanswer-area-crop"

#: Stands in for whatever a real response would quote back -- the recognized
#: answer text, or part of the request. Placed in response bodies below and
#: then asserted absent from every exception.
_SENSITIVE = "SENSITIVE-ANSWER-TEXT-MARKER"


def _serving(body: Any, *, status: int = 200) -> DocumentAiOCRProvider:
    def handle(request: httpx.Request) -> httpx.Response:
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    return document_ai_provider(httpx.MockTransport(handle))


def _raising(error: Exception) -> DocumentAiOCRProvider:
    def handle(request: httpx.Request) -> httpx.Response:
        raise error

    return document_ai_provider(httpx.MockTransport(handle))


def _captured(body: Any) -> tuple[DocumentAiOCRProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=body)

    return document_ai_provider(httpx.MockTransport(handle)), seen


# --------------------------------------------------------------------------- #
# What is sent
# --------------------------------------------------------------------------- #
def test_the_payload_is_the_crop_it_was_given_and_nothing_else() -> None:
    """Acceptance 3: 送信は回答欄の切り出しのみ。ページ全体を送らない.

    This adapter has no access to a page image at all -- the assertion is
    that it sends back exactly the bytes handed to it, so a caller that
    passes a crop cannot have a page sent on its behalf.
    """
    provider, seen = _captured(document_ai_body("光", ((0, 1, 0.95),)))

    provider.recognize(_CROP)

    payload = json.loads(seen[0].content)
    assert base64.b64decode(payload["rawDocument"]["content"]) == _CROP
    assert set(payload) == {"skipHumanReview", "rawDocument", "processOptions"}


def test_no_copy_is_left_in_a_human_review_queue() -> None:
    """Design section 26.2: "送信内容と応答を...残さない". Document AI's own
    human-review step would keep the crop on Google's side."""
    provider, seen = _captured(document_ai_body("光", ((0, 1, 0.95),)))

    provider.recognize(_CROP)

    assert json.loads(seen[0].content)["skipHumanReview"] is True


def test_the_language_hint_is_the_port_s_language_parameter() -> None:
    provider, seen = _captured(document_ai_body("光", ((0, 1, 0.95),)))

    provider.recognize(_CROP, language="ja")

    hints = json.loads(seen[0].content)["processOptions"]["ocrConfig"]["hints"]
    assert hints["languageHints"] == ["ja"]


def test_the_request_goes_to_the_processor_s_own_regional_host() -> None:
    provider, seen = _captured(document_ai_body("光", ((0, 1, 0.95),)))

    provider.recognize(_CROP)

    assert str(seen[0].url) == f"https://us-documentai.googleapis.com/v1/{PROCESSOR}:process"


def test_the_access_token_travels_only_in_the_authorization_header() -> None:
    provider, seen = _captured(document_ai_body("光", ((0, 1, 0.95),)))

    provider.recognize(_CROP)

    assert seen[0].headers["Authorization"] == "Bearer fake-access-token"
    assert "fake-access-token" not in seen[0].content.decode()


def test_a_jpeg_crop_is_declared_as_jpeg() -> None:
    provider, seen = _captured(document_ai_body("光", ((0, 1, 0.95),)))

    provider.recognize(b"\xff\xd8\xff-jpeg-crop")

    assert json.loads(seen[0].content)["rawDocument"]["mimeType"] == "image/jpeg"


# --------------------------------------------------------------------------- #
# What comes back
# --------------------------------------------------------------------------- #
def test_each_token_carries_its_own_slice_of_the_page_text() -> None:
    provider = _serving(document_ai_body("光合成が", ((0, 3, 0.95), (3, 4, 0.72))))

    result = provider.recognize(_CROP)

    assert result.text == "光合成が"
    assert [token.text for token in result.tokens] == ["光合成", "が"]
    assert result.provider == "document_ai"


def test_the_band_follows_the_confidence() -> None:
    provider = _serving(document_ai_body("あいう", ((0, 1, 0.99), (1, 2, 0.80), (2, 3, 0.30))))

    bands = [token.band for token in provider.recognize(_CROP).tokens]

    assert bands == [ConfidenceBand.HIGH, ConfidenceBand.MEDIUM, ConfidenceBand.LOW]


def test_a_rotated_token_becomes_its_enclosing_axis_aligned_box() -> None:
    """The port's box is axis-aligned; Document AI returns four corners that
    a tilted line of handwriting makes a rotated quadrilateral of."""
    body = {
        "document": {
            "text": "光",
            "pages": [
                {
                    "tokens": [
                        {
                            "layout": {
                                "textAnchor": {"textSegments": [{"endIndex": "1"}]},
                                "confidence": 0.9,
                                "boundingPoly": {
                                    "normalizedVertices": [
                                        {"x": 0.2, "y": 0.1},
                                        {"x": 0.8, "y": 0.2},
                                        {"x": 0.75, "y": 0.5},
                                        {"x": 0.15, "y": 0.4},
                                    ]
                                },
                            }
                        }
                    ]
                }
            ],
        }
    }

    box = _serving(body).recognize(_CROP).tokens[0].bounding_box

    assert (box.x, box.y) == pytest.approx((0.15, 0.1))
    assert (box.width, box.height) == pytest.approx((0.65, 0.4))


def test_a_vertex_past_the_edge_is_clamped_rather_than_failing_the_question() -> None:
    body = {
        "document": {
            "text": "光",
            "pages": [
                {
                    "tokens": [
                        {
                            "layout": {
                                "textAnchor": {"textSegments": [{"endIndex": "1"}]},
                                "confidence": 0.9,
                                "boundingPoly": {
                                    "normalizedVertices": [
                                        {"x": -0.0001, "y": 0.0},
                                        {"x": 1.0000001, "y": 1.0000001},
                                    ]
                                },
                            }
                        }
                    ]
                }
            ],
        }
    }

    box = _serving(body).recognize(_CROP).tokens[0].bounding_box

    assert (box.x, box.y, box.width, box.height) == (0.0, 0.0, 1.0, 1.0)


def test_a_token_with_no_polygon_keeps_its_reading() -> None:
    """Losing a real reading over a missing box would be the wrong trade --
    the box is only needed to place an annotation (design section 12.3)."""
    body = {
        "document": {
            "text": "光",
            "pages": [
                {
                    "tokens": [
                        {
                            "layout": {
                                "textAnchor": {"textSegments": [{"endIndex": "1"}]},
                                "confidence": 0.9,
                            }
                        }
                    ]
                }
            ],
        }
    }

    token = _serving(body).recognize(_CROP).tokens[0]

    assert token.text == "光"
    assert (token.bounding_box.width, token.bounding_box.height) == (1.0, 1.0)


def test_a_page_with_no_tokens_is_an_empty_reading_not_an_error() -> None:
    """ "The provider looked and found nothing" is a completed recognition.
    It is *not* the same as "this host has no OCR" -- that one raises
    `OCRUnavailable` and never gets here (Issue #114 acceptance 8)."""
    result = _serving({"document": {"text": "", "pages": [{"tokens": []}]}}).recognize(_CROP)

    assert result.text == ""
    assert result.tokens == ()


# --------------------------------------------------------------------------- #
# Failure classification
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, OCRRateLimitedError),
        (500, OCRServerError),
        (503, OCRServerError),
        (401, OCRProviderError),
        (403, OCRProviderError),
        (404, OCRProviderError),
    ],
)
def test_an_http_status_maps_to_the_exception_the_retry_policy_keys_off(
    status: int, expected: type[Exception]
) -> None:
    provider = _serving({"error": {"message": _SENSITIVE}}, status=status)

    with pytest.raises(expected) as error:
        provider.recognize(_CROP)

    assert str(status) in str(error.value)
    assert _SENSITIVE not in str(error.value)


def test_a_timeout_is_a_timeout() -> None:
    with pytest.raises(OCRTimeoutError):
        _raising(httpx.ReadTimeout("timed out")).recognize(_CROP)


def test_a_transport_failure_is_permanent_rather_than_uncategorized() -> None:
    with pytest.raises(OCRProviderError) as error:
        _raising(httpx.ConnectError("no route")).recognize(_CROP)

    assert "ConnectError" in str(error.value)
    assert "no route" not in str(error.value)


def test_a_body_that_is_not_json_is_a_schema_error() -> None:
    with pytest.raises(OCRResponseSchemaError):
        _serving(f"<html>{_SENSITIVE}</html>").recognize(_CROP)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"document": {"pages": [{"tokens": [{}]}]}},
        {"document": "not-an-object"},
        {"document": {"text": "光", "pages": "not-a-list"}},
    ],
)
def test_a_response_we_cannot_understand_is_a_schema_error_not_an_empty_reading(
    body: Any,
) -> None:
    """Collapsing the two would record "the student wrote nothing" for a
    response this code simply failed to read."""
    with pytest.raises(OCRResponseSchemaError):
        _serving(body).recognize(_CROP)


def test_an_omitted_confidence_is_zero_not_a_malformed_response() -> None:
    """proto3 omits a default, so a token Document AI is not at all sure of
    arrives with no ``confidence`` field. That is a real reading of "I looked
    and got nothing" -- the "本当に読めなかった" case, which stays low
    confidence and therefore still routes to a human. It is emphatically not
    the "this host has no OCR" case, which never reaches this adapter at all
    (Issue #114 acceptance 8).
    """
    body = {"document": {"text": "光", "pages": [{"tokens": [{"layout": {}}]}]}}

    token = _serving(body).recognize(_CROP).tokens[0]

    assert token.text == ""
    assert token.confidence == 0.0
    assert token.band is ConfidenceBand.LOW


def test_no_exception_ever_quotes_the_response_body() -> None:
    provider = _serving({"document": {"text": _SENSITIVE, "pages": "not-a-list"}})

    with pytest.raises(OCRResponseSchemaError) as error:
        provider.recognize(_CROP)

    assert _SENSITIVE not in str(error.value)


def test_no_exception_ever_quotes_the_processor_resource_name() -> None:
    """It carries the real GCP project id (AGENTS.md "Security"), and
    `RecognitionJobProcessor` puts an OCR failure into `Job.last_error`."""
    with pytest.raises(OCRProviderError) as error:
        _serving({"error": {}}, status=403).recognize(_CROP)

    assert PROCESSOR not in str(error.value)
    assert "test-project" not in str(error.value)


def test_the_adapter_refuses_a_processor_name_it_cannot_route() -> None:
    with pytest.raises(ValueError):
        DocumentAiOCRProvider(processor="projects/p/processors/id", tokens=fake_tokens())
