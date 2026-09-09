"""The coordinate chain detection and cropping share is exact (Issue #122).

**This file exists to keep a wrong answer from coming back.** Issue #122 was
reported as "the detected box is offset to the right", and the natural first
suspicion -- stated in the Issue itself -- was the page rotation: the real
answer sheets carry ``/Rotate`` 0, 90 and 270 mixed together, and a rotation
handled inconsistently between rendering and cropping would produce exactly
that symptom.

It is not the cause. Measured, the chain is exact to four decimal places on
every rotation, and the error is entirely in the detecting model's own
estimate (`domain.answer_area_snapping`). These tests hold that measurement
in place, so the next person to look at a misplaced box can rule the
transforms out in one test run instead of a day of investigation -- and so
that a "rotation fix" cannot be added here without the assertions saying it
was never broken.

The chain has exactly three links and no coordinate transform anywhere in
between:

1. `PdfEngine.render_page_png` rasterizes the page as displayed.
2. The box is stored as a fraction of that raster
   (`domain.profile.NormalizedBBox`).
3. `crop_normalized_rect` cuts that fraction back out of the same raster.

`domain.pdf_geometry` -- the only code that knows about ``/Rotate`` at all --
is used by neither step 1 nor step 3; its callers are the PDF annotation
export. Link 1's agreement with it is asserted below anyway, because it is
the assumption a reviewer's overlay is drawn on.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from auto_scoring.adapters.image.opencv_preprocessor import crop_normalized_rect
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.submission_intake import RENDER_SCALE
from auto_scoring.domain.models import NormalizedRect
from auto_scoring.domain.pdf_geometry import NormalizedPoint, PageGeometry, normalized_to_user_space

#: A landscape page, the shape the real vertical-writing answer sheets are
#: stored as before ``/Rotate`` turns them upright.
_PAGE_WIDTH_PT, _PAGE_HEIGHT_PT = 842.0, 595.0

#: One filled rectangle at a known place in PDF user space (origin bottom
#: left). Deliberately off-centre on both axes, so a mirrored or transposed
#: mapping cannot pass by symmetry.
_RECT_PT = (600.0, 400.0, 640.0, 520.0)

_ROTATIONS = (0, 90, 180, 270)


def _page_with_rectangle(tmp_path: Path, rotation: int) -> Path:
    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=(_PAGE_WIDTH_PT, _PAGE_HEIGHT_PT))
    pdf_canvas.setFillColorRGB(0, 0, 0)
    left, bottom, right, top = _RECT_PT
    pdf_canvas.rect(left, bottom, right - left, top - bottom, stroke=0, fill=1)
    pdf_canvas.save()

    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(buffer.getvalue())))
    writer.pages[0].rotation = rotation
    path = tmp_path / f"rotate-{rotation}.pdf"
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def _expected_displayed_box(geometry: PageGeometry) -> tuple[float, float, float, float]:
    """Where `domain.pdf_geometry` says `_RECT_PT` lands, as a fraction of
    the *displayed* page. Derived by inverting `normalized_to_user_space`,
    which is affine, over three sampled corners."""
    origin = normalized_to_user_space(NormalizedPoint(0.0, 0.0), geometry)
    along_x = normalized_to_user_space(NormalizedPoint(1.0, 0.0), geometry)
    along_y = normalized_to_user_space(NormalizedPoint(0.0, 1.0), geometry)
    ax, ay = along_x.x - origin.x, along_x.y - origin.y
    bx, by = along_y.x - origin.x, along_y.y - origin.y
    determinant = ax * by - ay * bx

    def to_normalized(user_x: float, user_y: float) -> tuple[float, float]:
        dx, dy = user_x - origin.x, user_y - origin.y
        return (dx * by - dy * bx) / determinant, (ax * dy - ay * dx) / determinant

    left, bottom, right, top = _RECT_PT
    corners = [to_normalized(x, y) for x in (left, right) for y in (bottom, top)]
    return (
        min(corner[0] for corner in corners),
        min(corner[1] for corner in corners),
        max(corner[0] for corner in corners),
        max(corner[1] for corner in corners),
    )


def _ink_mask(png_bytes: bytes) -> npt.NDArray[np.bool_]:
    decoded = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    assert decoded is not None
    return np.asarray(decoded < 128)


def _measured_displayed_box(png_bytes: bytes) -> tuple[float, float, float, float]:
    mask = _ink_mask(png_bytes)
    rows, columns = np.nonzero(mask)
    height, width = mask.shape
    return (
        float(columns.min()) / width,
        float(rows.min()) / height,
        float(columns.max() + 1) / width,
        float(rows.max() + 1) / height,
    )


@pytest.mark.parametrize("rotation", _ROTATIONS)
def test_rendering_agrees_with_the_page_geometry_on_every_rotation(
    tmp_path: Path, rotation: int
) -> None:
    """**Not a fix -- a measurement that rules a suspect out.**

    The rendered raster puts the rectangle exactly where
    `domain.pdf_geometry` says it is, for ``/Rotate`` 0, 90, 180 and 270.
    Issue #122's rightward offset therefore cannot come from rotation
    handling, and no compensation belongs anywhere in this path.
    """
    engine = PdfiumPypdfEngine()
    source = _page_with_rectangle(tmp_path, rotation)

    geometry = engine.page_geometry(source, 0)
    measured = _measured_displayed_box(engine.render_page_png(source, 0, scale=RENDER_SCALE))

    assert geometry.rotation == rotation
    # 1e-3 is one pixel at this render scale, not a loose tolerance: the
    # measurement is taken from whole pixels while the expectation is
    # continuous.
    assert measured == pytest.approx(_expected_displayed_box(geometry), abs=1e-3)


@pytest.mark.parametrize("rotation", _ROTATIONS)
def test_cropping_returns_exactly_the_region_it_was_given(tmp_path: Path, rotation: int) -> None:
    """The third link: cropping the measured box out of the same raster
    yields the rectangle and nothing else -- every pixel ink, none of the
    surrounding paper. A half-pixel disagreement between rendering and
    cropping would show up here as a coverage below 1.0."""
    engine = PdfiumPypdfEngine()
    source = _page_with_rectangle(tmp_path, rotation)
    page_png = engine.render_page_png(source, 0, scale=RENDER_SCALE)
    x0, y0, x1, y1 = _measured_displayed_box(page_png)

    cropped = crop_normalized_rect(
        page_png, NormalizedRect(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
    )

    assert float(_ink_mask(cropped).mean()) == 1.0


def test_detection_and_cropping_rasterize_the_same_way(tmp_path: Path) -> None:
    """Both ends of the chain must ask for the same raster.

    Detection renders the answer-layout PDF (`api.test_registration_router`)
    and cropping renders the submitted answer PDF
    (`adapters.submission_intake`), and the box measured on one is applied to
    the other. That only holds while both use `RENDER_SCALE`; a second scale
    introduced on either side would reopen this Issue as a genuine
    coordinate bug.
    """
    engine = PdfiumPypdfEngine()
    source = _page_with_rectangle(tmp_path, 270)

    first = engine.render_page_png(source, 0, scale=RENDER_SCALE)
    second = engine.render_page_png(source, 0, scale=RENDER_SCALE)

    assert _measured_displayed_box(first) == _measured_displayed_box(second)
