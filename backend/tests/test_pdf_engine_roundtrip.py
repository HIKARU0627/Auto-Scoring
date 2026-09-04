"""PoC 3 verification: a normalized point survives the engine -> pdfium round trip.

The app picks a point in ``0..1`` over the displayed page; ``PdfiumPypdfEngine``
converts it to user space and stamps it; pdfium (the same engine ``pdfrx`` wraps)
renders the result; we read the mark back and check it lands where the app asked,
within tolerance, across orientation / rotation / page size / CropBox, and
independent of render scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageChops
from pypdf import PdfWriter
from pypdf.generic import NameObject, NumberObject, RectangleObject

from auto_scoring.adapters.pdf import PdfiumPypdfEngine
from auto_scoring.domain.pdf_geometry import NormalizedPoint

# Max centroid error, in normalized units. Rasterizing at scale 2 and taking the
# mark's bounding-box centre lands within ~5e-4; an axis swap or missed rotation
# would be off by ~0.5. 4e-3 (~2.4 pt on A4) sits comfortably between.
_TOLERANCE = 4e-3

_A4_W, _A4_H = 595.0, 842.0
_LETTER_W, _LETTER_H = 612.0, 792.0


@dataclass(frozen=True)
class _Fixture:
    name: str
    media_width: float
    media_height: float
    rotation: int = 0
    crop: tuple[float, float, float, float] | None = None


_FIXTURES = [
    _Fixture("a4-portrait", _A4_W, _A4_H),
    _Fixture("a4-rotate-90", _A4_W, _A4_H, rotation=90),
    _Fixture("a4-rotate-180", _A4_W, _A4_H, rotation=180),
    _Fixture("a4-rotate-270", _A4_W, _A4_H, rotation=270),
    _Fixture("a4-landscape", _A4_H, _A4_W),
    _Fixture("letter-portrait", _LETTER_W, _LETTER_H),
    _Fixture("a4-cropbox-inset", _A4_W, _A4_H, crop=(30.0, 40.0, 565.0, 800.0)),
    _Fixture(
        "a4-cropbox-inset-rotate-90",
        _A4_W,
        _A4_H,
        rotation=90,
        crop=(30.0, 40.0, 565.0, 800.0),
    ),
]

_TEST_POINTS = [
    NormalizedPoint(0.12, 0.15),
    NormalizedPoint(0.5, 0.5),
    NormalizedPoint(0.9, 0.25),
    NormalizedPoint(0.25, 0.88),
    NormalizedPoint(0.82, 0.8),
]


def _write_fixture(fixture: _Fixture, path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=fixture.media_width, height=fixture.media_height)
    if fixture.rotation:
        page[NameObject("/Rotate")] = NumberObject(fixture.rotation)
    if fixture.crop is not None:
        page[NameObject("/CropBox")] = RectangleObject(list(fixture.crop))
    with path.open("wb") as handle:
        writer.write(handle)


def _measure_red_centroid(png_bytes: bytes) -> NormalizedPoint:
    with Image.open(BytesIO(png_bytes)) as image:
        rgb = image.convert("RGB")
    red, green, _ = rgb.split()
    redness = ImageChops.subtract(red, green).point(lambda v: 255 if v > 80 else 0)
    box = redness.getbbox()
    if box is None:
        raise AssertionError("stamped mark not found in the rendered page")
    left, top, right, bottom = box
    width, height = rgb.size
    return NormalizedPoint(
        x=(left + right) / 2 / width,
        y=(top + bottom) / 2 / height,
    )


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda f: f.name)
def test_stamped_point_renders_where_the_app_asked(fixture: _Fixture, tmp_path: Path) -> None:
    engine = PdfiumPypdfEngine()
    source = tmp_path / f"{fixture.name}.pdf"
    _write_fixture(fixture, source)

    for index, point in enumerate(_TEST_POINTS):
        stamped = tmp_path / f"{fixture.name}-{index}.pdf"
        engine.stamp_markers(source, stamped, {0: [point]})
        measured = _measure_red_centroid(engine.render_page_png(stamped, 0, scale=2.0))
        assert measured.x == pytest.approx(point.x, abs=_TOLERANCE)
        assert measured.y == pytest.approx(point.y, abs=_TOLERANCE)


def test_result_is_independent_of_render_scale(tmp_path: Path) -> None:
    engine = PdfiumPypdfEngine()
    source = tmp_path / "scale.pdf"
    _write_fixture(_Fixture("scale", _A4_W, _A4_H, rotation=90), source)
    stamped = tmp_path / "scale-stamped.pdf"
    point = NormalizedPoint(0.3, 0.7)
    engine.stamp_markers(source, stamped, {0: [point]})

    for scale in (1.0, 2.0, 3.5):
        measured = _measure_red_centroid(engine.render_page_png(stamped, 0, scale=scale))
        assert measured.x == pytest.approx(point.x, abs=_TOLERANCE)
        assert measured.y == pytest.approx(point.y, abs=_TOLERANCE)


def test_page_geometry_reads_rotation_and_cropbox(tmp_path: Path) -> None:
    source = tmp_path / "geometry.pdf"
    _write_fixture(
        _Fixture("geometry", _A4_W, _A4_H, rotation=90, crop=(30.0, 40.0, 565.0, 800.0)),
        source,
    )
    geometry = PdfiumPypdfEngine().page_geometry(source, 0)
    assert geometry.rotation == 90
    assert (geometry.crop_offset_x, geometry.crop_offset_y) == pytest.approx((30.0, 40.0))
    assert (geometry.crop_width, geometry.crop_height) == pytest.approx((535.0, 760.0))
    # quarter turn -> displayed dimensions are swapped
    assert (geometry.displayed_width, geometry.displayed_height) == pytest.approx((760.0, 535.0))
