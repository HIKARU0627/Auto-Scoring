"""Contract every :class:`OCRProvider` implementation must satisfy.

``OCRProviderContract`` is the reusable part: a real adapter subclasses it and
overrides the ``provider`` and ``unreadable_image`` fixtures.
`DocumentAiOCRProvider` (Issue #114) is the shipped one and does exactly that,
against a `httpx.MockTransport` serving recorded-shape responses -- no
network, no credentials, so it runs in ordinary CI.

``_StubOCRProvider`` is test-only scaffolding from Issue #13, kept because it
exercises the contract from a second, deliberately different direction (an
in-memory provider with no HTTP at all). It is not an OCR candidate and must
never move into ``src/``.
"""

import base64
import json
from typing import Any

import httpx
import pytest
from google.auth.credentials import Credentials

from auto_scoring.adapters.ai_grading._google_adc import AdcTokenSource
from auto_scoring.adapters.ocr.document_ai_provider import DocumentAiOCRProvider
from auto_scoring.domain.ocr import (
    BoundingBox,
    ConfidenceBand,
    OCRProvider,
    OcrResult,
    OcrToken,
)

#: A processor resource name shaped like the real thing but pointing nowhere.
PROCESSOR = "projects/test-project/locations/us/processors/testprocessor"

#: The crop the contract's ``unreadable_image`` fixture sends. Distinct
#: bytes so the mock transport can answer it differently.
UNREADABLE_IMAGE = b"\x89PNG\r\n\x1a\nunreadable"


class FakeAdcCredentials(Credentials):
    """ADC credentials that are always valid and never hit the network."""

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.token = "fake-access-token"

    def refresh(self, request: object) -> None:
        self.token = "fake-access-token"


def fake_tokens() -> AdcTokenSource:
    return AdcTokenSource(credentials=FakeAdcCredentials(), project_id="test-project")


def document_ai_body(text: str, tokens: tuple[tuple[int, int, float], ...]) -> dict[str, Any]:
    """One ``:process`` response, in Document AI's own shape.

    ``tokens`` is ``(start, end, confidence)`` per token; the boxes are
    generated so that each token occupies its own horizontal band. Indices
    are JSON strings and ``startIndex`` is omitted when zero, because that is
    what Document AI actually sends (int64 fields, and proto3 omits
    defaults) -- a fixture that pre-normalized those would not exercise the
    parsing this adapter has to do.
    """
    page_tokens = []
    for index, (start, end, confidence) in enumerate(tokens):
        top = index / max(len(tokens), 1)
        anchor: dict[str, Any] = {"endIndex": str(end)}
        if start:
            anchor["startIndex"] = str(start)
        page_tokens.append(
            {
                "layout": {
                    "textAnchor": {"textSegments": [anchor]},
                    "confidence": confidence,
                    "boundingPoly": {
                        "normalizedVertices": [
                            {"x": 0.1, "y": top},
                            {"x": 0.9, "y": top},
                            {"x": 0.9, "y": top + 0.05},
                            {"x": 0.1, "y": top + 0.05},
                        ]
                    },
                }
            }
        )
    return {"document": {"text": text, "pages": [{"tokens": page_tokens}]}}


def document_ai_provider(handler: httpx.MockTransport) -> DocumentAiOCRProvider:
    return DocumentAiOCRProvider(
        processor=PROCESSOR, tokens=fake_tokens(), client=httpx.Client(transport=handler)
    )


class OCRProviderContract:
    """Mix-in of provider-agnostic checks. Not collected on its own."""

    @pytest.fixture
    def provider(self) -> OCRProvider:
        raise NotImplementedError

    @pytest.fixture
    def readable_image(self) -> bytes:
        return b"\x89PNG\r\n\x1a\n"

    @pytest.fixture
    def unreadable_image(self) -> bytes | None:
        return None

    def test_declares_a_name(self, provider: OCRProvider) -> None:
        assert isinstance(provider, OCRProvider)
        assert provider.name

    def test_recognize_returns_result_with_well_formed_tokens(
        self, provider: OCRProvider, readable_image: bytes
    ) -> None:
        result = provider.recognize(readable_image)
        assert isinstance(result, OcrResult)
        for token in result.tokens:
            assert 0.0 <= token.confidence <= 1.0
            assert isinstance(token.band, ConfidenceBand)

    def test_unreadable_span_is_low_confidence_not_dropped(
        self, provider: OCRProvider, unreadable_image: bytes | None
    ) -> None:
        if unreadable_image is None:
            pytest.skip("no unreadable_image fixture provided")
        result = provider.recognize(unreadable_image)
        assert result.tokens, "an unreadable region must still yield a candidate token"
        assert result.has_low_confidence


class _StubOCRProvider:
    name = "stub"

    def recognize(self, image: bytes, *, language: str = "ja") -> OcrResult:
        if image == b"unreadable":
            return OcrResult(
                text="",
                tokens=(
                    OcrToken(
                        text="",
                        bounding_box=BoundingBox(0.10, 0.40, 0.15, 0.05),
                        confidence=0.12,
                        band=ConfidenceBand.LOW,
                    ),
                ),
                provider=self.name,
            )
        return OcrResult(
            text="光合成",
            tokens=(
                OcrToken(
                    text="光合成",
                    bounding_box=BoundingBox(0.10, 0.20, 0.20, 0.05),
                    confidence=0.96,
                    band=ConfidenceBand.HIGH,
                ),
            ),
            provider=self.name,
        )


class TestStubOCRProviderContract(OCRProviderContract):
    @pytest.fixture
    def provider(self) -> _StubOCRProvider:
        return _StubOCRProvider()

    @pytest.fixture
    def unreadable_image(self) -> bytes:
        return b"unreadable"


class TestDocumentAiOCRProviderContract(OCRProviderContract):
    """`DocumentAiOCRProvider` (Issue #114) is the shipped adapter for the
    OCR service business-rules-and-evaluation-data.md section 3 (A) adopted
    (Google Document AI, Issue #81). It has to satisfy the same contract the
    stub above does.

    The "unreadable" case is a real Document AI shape, not an invented one:
    a token it read but is not confident about still comes back, with a low
    ``layout.confidence`` -- which is exactly what `domain.ocr.OcrToken`'s
    docstring requires an adapter to preserve rather than drop or replace
    with a guess. The handler branches on the *image it was sent*, which
    also pins that the adapter sends the caller's bytes and not something
    else.
    """

    @pytest.fixture
    def unreadable_image(self) -> bytes:
        return UNREADABLE_IMAGE

    @pytest.fixture
    def provider(self) -> DocumentAiOCRProvider:
        def handle(request: httpx.Request) -> httpx.Response:
            sent = base64.b64decode(json.loads(request.content)["rawDocument"]["content"])
            if sent == UNREADABLE_IMAGE:
                return httpx.Response(200, json=document_ai_body("?", ((0, 1, 0.11),)))
            return httpx.Response(200, json=document_ai_body("光合成", ((0, 3, 0.97),)))

        return document_ai_provider(httpx.MockTransport(handle))
