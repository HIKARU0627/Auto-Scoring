"""Measuring the red ink an export actually put on a page.

Rasterize and look for reddish pixels -- the methodology PoC 3's
`test_pdf_engine_roundtrip.py` established and `test_pdf_annotation_rendering.py`
extended. It lives here now that the end-to-end tests need it too: Issue #120
found that an export could run to success and produce a PDF with nothing
drawn on it, and the test that came closest to catching that asserted
``output != source`` on two `Path` objects -- true for any two different
filenames, including a byte-for-byte copy. A blank page has to be something a
test can actually see.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageChops

from auto_scoring.domain.models import NormalizedRect

#: How much redder than green a pixel must be to count as ink rather than
#: rasterization noise or a dark line in the scan underneath.
_REDNESS_THRESHOLD = 60


def _redness(image: Image.Image) -> Image.Image:
    red, green, _ = image.convert("RGB").split()
    return ImageChops.subtract(red, green).point(
        lambda value: 255 if value > _REDNESS_THRESHOLD else 0
    )


def redness_bbox(png_bytes: bytes) -> tuple[int, int, int, int] | None:
    """The bounding box of every reddish pixel on the page, or ``None`` for a
    page with no ink on it at all."""
    with Image.open(BytesIO(png_bytes)) as image:
        return _redness(image).getbbox()


def has_red_within(png_bytes: bytes, rect: NormalizedRect, *, margin: float = 0.03) -> bool:
    """Whether any reddish pixel exists inside ``rect`` (expanded by
    ``margin`` on every side, to absorb rasterization/stroke-width slop) --
    checked on a crop of just that region, so multiple marks elsewhere on
    the same page never affect this rect's own result.
    """
    with Image.open(BytesIO(png_bytes)) as image:
        rgb = image.convert("RGB")
    width, height = rgb.size
    left = max(0, int((rect.x - margin) * width))
    top = max(0, int((rect.y - margin) * height))
    right = min(width, int((rect.x + rect.width + margin) * width))
    bottom = min(height, int((rect.y + rect.height + margin) * height))
    return _redness(rgb.crop((left, top, right, bottom))).getbbox() is not None
