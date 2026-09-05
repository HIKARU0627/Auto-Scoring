"""Adapter tests for the OpenCV image preprocessor (Issue #17 §7.1)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from auto_scoring.adapters.image.opencv_preprocessor import (
    OpenCvImagePreprocessor,
    crop_normalized_rect,
)
from auto_scoring.domain.models import NormalizedRect


def _encode_png(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def _rotated_page(angle_deg: float) -> bytes:
    image = np.full((400, 300, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (50, 50), (250, 100), (0, 0, 0), -1)
    cv2.rectangle(image, (50, 150), (250, 170), (0, 0, 0), -1)
    matrix = cv2.getRotationMatrix2D((150, 200), angle_deg, 1.0)
    rotated = cv2.warpAffine(image, matrix, (300, 400), borderValue=(255, 255, 255))
    return _encode_png(rotated)


def test_preprocess_page_corrects_a_skewed_page() -> None:
    preprocessor = OpenCvImagePreprocessor()
    result = preprocessor.preprocess_page(_rotated_page(4.0))

    assert result.rotation_correction_deg == pytest.approx(-4.0, abs=0.5)
    decoded = cv2.imdecode(np.frombuffer(result.png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape == (400, 300, 3)


def test_preprocess_page_leaves_a_straight_page_uncorrected() -> None:
    preprocessor = OpenCvImagePreprocessor()
    result = preprocessor.preprocess_page(_rotated_page(0.0))

    assert result.rotation_correction_deg == 0.0


def test_preprocess_page_rejects_undecodable_bytes() -> None:
    preprocessor = OpenCvImagePreprocessor()
    with pytest.raises(ValueError, match="decode"):
        preprocessor.preprocess_page(b"not a png")


def test_crop_normalized_rect_extracts_the_expected_region() -> None:
    image = np.zeros((200, 100, 3), dtype=np.uint8)
    image[:, :, :] = (0, 0, 0)
    image[100:200, 0:100] = (255, 255, 255)  # bottom half white, top half black
    png_bytes = _encode_png(image)

    rect = NormalizedRect(x=0.0, y=0.5, width=1.0, height=0.5)
    cropped_bytes = crop_normalized_rect(png_bytes, rect)
    cropped = cv2.imdecode(np.frombuffer(cropped_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert cropped is not None
    assert cropped.shape[0] == pytest.approx(100, abs=1)
    assert cropped.shape[1] == pytest.approx(100, abs=1)
    assert cropped.mean() > 200  # cropped the white half, not the black half


def test_crop_normalized_rect_clamps_to_image_bounds() -> None:
    image = np.full((50, 50, 3), 128, dtype=np.uint8)
    png_bytes = _encode_png(image)

    rect = NormalizedRect(x=0.0, y=0.0, width=1.0, height=1.0)
    cropped_bytes = crop_normalized_rect(png_bytes, rect)
    cropped = cv2.imdecode(np.frombuffer(cropped_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert cropped is not None
    assert cropped.shape[:2] == (50, 50)


def test_crop_normalized_rect_rejects_undecodable_bytes() -> None:
    with pytest.raises(ValueError, match="decode"):
        crop_normalized_rect(b"not a png", NormalizedRect(x=0, y=0, width=1, height=1))
