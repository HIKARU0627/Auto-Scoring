"""Contract every :class:`OCRProvider` implementation must satisfy.

``OCRProviderContract`` is the reusable part: when PoC 1 (Issue #13) promotes a
real adapter, add a test class that subclasses it and overrides the ``provider``
and ``unreadable_image`` fixtures. ``_StubOCRProvider`` is test-only scaffolding
that keeps the contract exercised until then -- it is not an OCR candidate and
must never move into ``src/`` (Issue #13 promotion condition).
"""

import pytest

from auto_scoring.adapters.ocr.null_provider import NullOCRProvider
from auto_scoring.domain.ocr import (
    BoundingBox,
    ConfidenceBand,
    OCRProvider,
    OcrResult,
    OcrToken,
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


class TestNullOCRProviderContract(OCRProviderContract):
    """`NullOCRProvider` (Issue #19) is the real, shipped placeholder
    adapter until business-rules-and-evaluation-data.md section 3 (A) is
    decided -- it must satisfy the same contract as any real candidate."""

    @pytest.fixture
    def provider(self) -> NullOCRProvider:
        return NullOCRProvider()

    @pytest.fixture
    def unreadable_image(self) -> bytes:
        return b"anything -- NullOCRProvider never reads the image"
