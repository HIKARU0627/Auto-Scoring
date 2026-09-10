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
    UnreadableSpans,
    lowest_token_confidence,
    unreadable_spans,
)

#: Stands in for `RecognitionSettings.confidence_threshold`; never a literal
#: in an assertion (business rules §3.1 (C)), and the token qualities below
#: are chosen relative to it.
_THRESHOLD = 0.80


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


def test_lowest_token_confidence_is_the_minimum_token_confidence() -> None:
    high = OcrToken("a", BoundingBox(0.0, 0.0, 0.1, 0.1), 0.9, ConfidenceBand.HIGH)
    low = OcrToken("?", BoundingBox(0.2, 0.2, 0.1, 0.1), 0.2, ConfidenceBand.LOW)
    assert lowest_token_confidence(OcrResult(text="a?", tokens=(high, low))) == pytest.approx(0.2)


def test_lowest_token_confidence_is_zero_with_no_tokens() -> None:
    assert lowest_token_confidence(OcrResult(text="")) == 0.0


# --------------------------------------------------------------------------- #
# Unreadable spans (Issue #158)
# --------------------------------------------------------------------------- #
def _reading(*confidences: float) -> OcrResult:
    """A reading of ``len(confidences)`` spans laid out left to right.

    The boxes are only wide enough to stay inside the page; nothing here
    depends on where they are, only on there being one per span.
    """
    width = 1.0 / (len(confidences) + 1)
    return OcrResult(
        text="".join("x" for _ in confidences),
        tokens=tuple(
            OcrToken(
                text="x",
                bounding_box=BoundingBox(index * width, 0.1, width, 0.05),
                confidence=confidence,
                band=(
                    ConfidenceBand.HIGH
                    if confidence >= 0.9
                    else ConfidenceBand.MEDIUM
                    if confidence >= 0.7
                    else ConfidenceBand.LOW
                ),
            )
            for index, confidence in enumerate(confidences)
        ),
        provider="test",
    )


def test_unreadable_spans_reports_which_spans_fell_below_the_threshold() -> None:
    spans = unreadable_spans(_reading(0.95, 0.31, 0.88, 0.12), minimum_confidence=_THRESHOLD)

    assert spans.token_count == 4
    assert spans.indices == (1, 3)  # *where*, not just how many
    assert spans.count == 2
    assert spans.readable_count == 2
    assert spans.nothing_readable is False


def test_unreadable_spans_of_a_reading_with_no_tokens_is_nothing_readable() -> None:
    spans = unreadable_spans(OcrResult(text=""), minimum_confidence=_THRESHOLD)

    assert spans.token_count == 0
    assert spans.count == 0
    assert spans.nothing_readable is True


def test_a_reading_whose_every_span_is_unreadable_is_nothing_readable() -> None:
    spans = unreadable_spans(_reading(0.3, 0.1, 0.2), minimum_confidence=_THRESHOLD)

    assert spans.count == 3
    assert spans.nothing_readable is True


@pytest.mark.parametrize("length", range(1, 41))
def test_writing_more_of_the_same_quality_never_turns_a_reading_unreadable(
    length: int,
) -> None:
    """The property Issue #158 exists for, and the one a single example
    cannot pin: **length must not decide this.**

    Each span is drawn from the same fixed mixture of qualities -- some above
    the threshold, some below -- so a longer reading here is a longer answer
    in the same handwriting, not a worse one. `lowest_token_confidence`, the
    aggregate this used to gate on, cannot survive that: it is a minimum, so
    every additional draw can only push it down, and by three spans it is
    already under the threshold (asserted below so the two behaviours are
    visible side by side).

    On the 15 recorded readings of 2026-09-09 that is exactly what happened
    -- every reading of 5 spans or fewer passed and every one of 9 or more
    failed, with correctness playing no part
    (docs/ocr-recognition-pipeline.md §9).
    """
    qualities = [0.97, 0.85, 0.62]  # the third is below any sane threshold
    reading = _reading(*[qualities[i % len(qualities)] for i in range(length)])

    spans = unreadable_spans(reading, minimum_confidence=_THRESHOLD)

    assert spans.nothing_readable is False, "a readable span stayed readable"
    if length >= 3:
        assert lowest_token_confidence(reading) < _THRESHOLD, (
            "the old aggregate must still be shown to fail here -- "
            "otherwise this test would pass for the wrong reason"
        )


def test_unreadable_span_count_grows_with_length_and_so_is_never_the_gate() -> None:
    """Why the *count* carries no threshold of its own (Issue #158).

    Three answers in the same handwriting, one span in ten unreadable. The
    count rises with length exactly as the minimum falls, so any cut on it
    would rebuild the defect one level up; what does not move is that each
    reading still has readable spans.
    """
    pattern = [0.95] * 9 + [0.4]
    counts = []
    for repeats in (1, 2, 5):
        spans = unreadable_spans(_reading(*(pattern * repeats)), minimum_confidence=_THRESHOLD)
        counts.append(spans.count)
        assert spans.nothing_readable is False

    assert counts == [1, 2, 5]


def test_unreadable_spans_rejects_positions_outside_the_reading() -> None:
    with pytest.raises(ValueError, match="ascending positions"):
        UnreadableSpans(token_count=2, indices=(2,))


def test_unreadable_spans_rejects_unordered_positions() -> None:
    with pytest.raises(ValueError, match="ascending positions"):
        UnreadableSpans(token_count=3, indices=(1, 1))


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
