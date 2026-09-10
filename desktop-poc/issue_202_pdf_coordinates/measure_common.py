"""Shared measurement helpers for PoC 6."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageChops

from auto_scoring.domain.pdf_geometry import NormalizedPoint

TOLERANCE = 4e-3
RENDER_SCALE = 2.0


def measure_red_centroid(png_bytes: bytes) -> NormalizedPoint:
    with Image.open(BytesIO(png_bytes)) as image:
        rgb = image.convert("RGB")
    red, green, _ = rgb.split()
    redness = ImageChops.subtract(red, green).point(lambda value: 255 if value > 80 else 0)
    box = redness.getbbox()
    if box is None:
        raise RuntimeError("stamped mark not found in the rendered page")
    left, top, right, bottom = box
    width, height = rgb.size
    return NormalizedPoint((left + right) / 2 / width, (top + bottom) / 2 / height)


def max_error(expected: NormalizedPoint, measured: NormalizedPoint) -> float:
    return max(abs(measured.x - expected.x), abs(measured.y - expected.y))
