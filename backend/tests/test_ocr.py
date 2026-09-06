"""Unit tests for the OCR domain types and the ``OCRProvider`` port."""

import pytest

from auto_scoring.domain.ocr import (
    BoundingBox,
    ConfidenceBand,
    OCRProvider,
    OCRProviderError,
    OCRRateLimitedError,
    OCRResponseSchemaError,
    OcrResult,
    OCRServerError,
    OCRTimeoutError,
    OcrToken,
    overall_confidence,
)


def test_bounding_box_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match=r"within \[0.0, 1.0\]"):
        BoundingBox(x=1.5, y=0.0, width=0.1, height=0.1)


def test_bounding_box_rejects_overflow() -> None:
    with pytest.raises(ValueError, match="x \\+ width"):
        BoundingBox(x=0.6, y=0.0, width=0.6, height=0.1)


def test_bounding_box_center_and_area() -> None:
    box = BoundingBox(x=0.2, y=0.4, width=0.4, height=0.2)
    assert box.center == pytest.approx((0.4, 0.5))
    assert box.area == pytest.approx(0.08)


def test_bounding_box_iou_identical_and_disjoint() -> None:
    box = BoundingBox(x=0.1, y=0.1, width=0.2, height=0.2)
    assert box.iou(box) == pytest.approx(1.0)
    far = BoundingBox(x=0.8, y=0.8, width=0.1, height=0.1)
    assert box.iou(far) == 0.0


def test_bounding_box_iou_half_overlap() -> None:
    left = BoundingBox(x=0.0, y=0.0, width=0.2, height=0.2)
    right = BoundingBox(x=0.1, y=0.0, width=0.2, height=0.2)
    assert left.iou(right) == pytest.approx(1.0 / 3.0)


def test_ocr_token_rejects_confidence_out_of_range() -> None:
    with pytest.raises(ValueError, match="confidence"):
        OcrToken(
            text="x",
            bounding_box=BoundingBox(0.0, 0.0, 0.1, 0.1),
            confidence=1.5,
            band=ConfidenceBand.HIGH,
        )


def test_confidence_band_parses_from_string() -> None:
    assert ConfidenceBand("low") is ConfidenceBand.LOW


def test_ocr_result_flags_low_confidence_token() -> None:
    high = OcrToken("a", BoundingBox(0.0, 0.0, 0.1, 0.1), 0.9, ConfidenceBand.HIGH)
    low = OcrToken("?", BoundingBox(0.2, 0.2, 0.1, 0.1), 0.1, ConfidenceBand.LOW)
    assert OcrResult(text="a", tokens=(high,)).has_low_confidence is False
    assert OcrResult(text="a", tokens=(high, low)).has_low_confidence is True


def test_ocr_result_from_mapping_round_trips() -> None:
    data = {
        "text": "光合成",
        "provider": "recorded-fixture",
        "tokens": [
            {
                "text": "光合成",
                "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.05},
                "confidence": 0.95,
                "band": "high",
            }
        ],
    }
    result = OcrResult.from_mapping(data)
    assert result.text == "光合成"
    assert result.provider == "recorded-fixture"
    assert result.tokens[0].band is ConfidenceBand.HIGH
    assert result.tokens[0].bounding_box.width == pytest.approx(0.2)


def test_overall_confidence_is_the_minimum_token_confidence() -> None:
    high = OcrToken("a", BoundingBox(0.0, 0.0, 0.1, 0.1), 0.9, ConfidenceBand.HIGH)
    low = OcrToken("?", BoundingBox(0.2, 0.2, 0.1, 0.1), 0.2, ConfidenceBand.LOW)
    assert overall_confidence(OcrResult(text="a?", tokens=(high, low))) == pytest.approx(0.2)


def test_overall_confidence_is_zero_with_no_tokens() -> None:
    assert overall_confidence(OcrResult(text="")) == 0.0


@pytest.mark.parametrize(
    "error_type", [OCRTimeoutError, OCRRateLimitedError, OCRServerError, OCRResponseSchemaError]
)
def test_ocr_provider_errors_are_ocr_provider_error(error_type: type[OCRProviderError]) -> None:
    assert issubclass(error_type, OCRProviderError)


def test_runtime_checkable_accepts_minimal_implementation() -> None:
    class _Minimal:
        name = "minimal"

        def recognize(self, image: bytes, *, language: str = "ja") -> OcrResult:
            return OcrResult(text="", provider=self.name)

    assert isinstance(_Minimal(), OCRProvider)
    assert not isinstance(object(), OCRProvider)
