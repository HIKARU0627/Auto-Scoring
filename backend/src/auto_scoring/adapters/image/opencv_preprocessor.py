"""OpenCV-backed :class:`~auto_scoring.domain.image_preprocess.ImagePreprocessor`.

Implements simplified-design-specification.md §7.1's four preview corrections:

* 傾き補正 / 回転補正 -- small-angle deskew via ``cv2.minAreaRect`` on the ink
  mask, then ``cv2.warpAffine`` about the image center (canvas size unchanged,
  so it never shifts the normalized coordinate frame -- see
  ``docs/answer-intake-and-preprocessing.md`` §3).
* 拡大縮小補正 -- handled upstream by rendering every page at the same fixed
  ``scale`` via ``PdfEngine.render_page_png``, so this step always receives a
  consistently-scaled raster regardless of the source page's physical size.
* ノイズ低減 -- ``cv2.fastNlMeansDenoisingColored``.
* コントラスト調整 -- CLAHE on the L channel in LAB space (avoids blowing out
  color balance the way a naive global histogram equalization would).
"""

from __future__ import annotations

import cv2
import numpy as np

from auto_scoring.domain.image_preprocess import PreprocessedPage
from auto_scoring.domain.models import NormalizedRect

#: Skew angles below this are treated as scan noise, not real skew.
_MIN_SKEW_CORRECTION_DEG = 0.3
#: Cap correction so a page that is deliberately landscape/rotated 90/180/270
#: (handled by the PDF's own /Rotate, already applied by the renderer) is
#: never mistaken for a few-degree skew.
_MAX_SKEW_CORRECTION_DEG = 10.0


class OpenCvImagePreprocessor:
    """Concrete :class:`~auto_scoring.domain.image_preprocess.ImagePreprocessor`."""

    def preprocess_page(self, png_bytes: bytes) -> PreprocessedPage:
        buffer = np.frombuffer(png_bytes, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("could not decode page image")

        angle = _estimate_skew_deg(image)
        corrected = _rotate(image, angle) if abs(angle) >= _MIN_SKEW_CORRECTION_DEG else image
        denoised = cv2.fastNlMeansDenoisingColored(corrected, None, 6, 6, 7, 21)
        contrasted = _apply_clahe(denoised)

        ok, encoded = cv2.imencode(".png", contrasted)
        if not ok:
            raise ValueError("could not encode processed page image")
        applied = angle if abs(angle) >= _MIN_SKEW_CORRECTION_DEG else 0.0
        return PreprocessedPage(png_bytes=encoded.tobytes(), rotation_correction_deg=applied)


def _estimate_skew_deg(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    inverted = cv2.bitwise_not(gray)
    _, thresh = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    # cv2.minAreaRect reports the rotation of its box in [-90, 0); a box close
    # to axis-aligned but rotated *the other way* gets reported near -90
    # rather than near 0, so fold that back into a small rotation around 0.
    if angle < -45:
        angle = 90 + angle
    return float(max(-_MAX_SKEW_CORRECTION_DEG, min(_MAX_SKEW_CORRECTION_DEG, angle)))


def _rotate(image: np.ndarray, angle_deg: float) -> np.ndarray:
    height, width = image.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def crop_normalized_rect(png_bytes: bytes, rect: NormalizedRect) -> bytes:
    """Crop ``rect`` (top-left origin, ``0..1``) out of a rendered page PNG.

    Used by ``adapters.submission_intake`` to cut a question's answer-area
    image out of the *untouched* raster (never the deskewed preview -- see
    ``docs/answer-intake-and-preprocessing.md`` §3).
    """
    buffer = np.frombuffer(png_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("could not decode page image")
    height, width = int(image.shape[0]), int(image.shape[1])
    x0 = max(0, min(width - 1, round(rect.x * width)))
    y0 = max(0, min(height - 1, round(rect.y * height)))
    x1 = max(x0 + 1, min(width, round((rect.x + rect.width) * width)))
    y1 = max(y0 + 1, min(height, round((rect.y + rect.height) * height)))
    cropped = image[y0:y1, x0:x1]
    ok, encoded = cv2.imencode(".png", cropped)
    if not ok:
        raise ValueError("could not encode cropped answer image")
    return encoded.tobytes()


def _apply_clahe(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    merged = cv2.merge((l_channel, a_channel, b_channel))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
