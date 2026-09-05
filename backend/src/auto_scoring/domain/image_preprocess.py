"""Port for the per-page image preprocessing step (simplified-design-spec.md
§7.1: 傾き補正・回転補正・拡大縮小補正・ノイズ低減・コントラスト調整).

The concrete OpenCV implementation lives in
``adapters/image/opencv_preprocessor.py`` -- the domain only ever sees this
protocol, mirroring how :mod:`auto_scoring.domain.pdf_engine` isolates
pypdfium2/pypdf (``AGENTS.md``: domain must not import an external SDK).

Design decision (``docs/answer-intake-and-preprocessing.md`` §3): this step
only touches the *preview* image shown to a human. Per-question answer-area
cropping uses the untouched raster from ``PdfEngine.render_page_png`` against
the test's confirmed ``Question.answer_area`` coordinates, so a cosmetic
deskew here can never misalign a crop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class PreprocessedPage:
    """Result of running one rasterized page through the preprocessing step."""

    png_bytes: bytes
    #: Degrees of skew correction actually applied (0.0 if within tolerance).
    #: Diagnostic only -- never used to transform other coordinates.
    rotation_correction_deg: float


class ImagePreprocessor(Protocol):
    def preprocess_page(self, png_bytes: bytes) -> PreprocessedPage:
        """Deskew, denoise and normalize contrast on one rasterized page image."""
        ...
