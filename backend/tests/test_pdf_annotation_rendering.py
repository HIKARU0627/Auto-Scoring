"""Integration tests for `PdfiumPypdfEngine.render_annotations` (Issue #23).

Real pypdf + pdfium, same "stamp then rasterize and measure red pixels"
methodology PoC 3's own `test_pdf_engine_roundtrip.py` established -- these
extend it to the richer marks (circle/cross/triangle/underline/box/score/
comment) Issue #23 adds, including Japanese comment text, multi-page
placement, rotation, and a missing-font failure.
"""

from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject, RectangleObject

import auto_scoring.adapters.pdf.pdfium_pypdf_engine as engine_module
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import (
    JapaneseFontNotFoundError,
    PdfiumPypdfEngine,
)
from auto_scoring.domain.models import AnnotationKind, NormalizedRect
from auto_scoring.domain.pdf_engine import AnnotationMark

_A4_W, _A4_H = 595.0, 842.0


def _write_pdf(path: Path, *, pages: int = 1, rotation: int = 0) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=_A4_W, height=_A4_H)
        if rotation:
            page[NameObject("/Rotate")] = NumberObject(rotation)
    with path.open("wb") as handle:
        writer.write(handle)


def _write_pdf_with_mediabox_offset(path: Path, *, offset: tuple[float, float]) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=_A4_W, height=_A4_H)
    left, bottom = offset
    page.mediabox = RectangleObject((left, bottom, left + _A4_W, bottom + _A4_H))
    with path.open("wb") as handle:
        writer.write(handle)


def _redness_bbox(png_bytes: bytes) -> tuple[int, int, int, int] | None:
    with Image.open(BytesIO(png_bytes)) as image:
        rgb = image.convert("RGB")
    red, green, _ = rgb.split()
    redness = ImageChops.subtract(red, green).point(lambda v: 255 if v > 60 else 0)
    return redness.getbbox()


def _has_red_within(png_bytes: bytes, rect: NormalizedRect, *, margin: float = 0.03) -> bool:
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
    cropped = rgb.crop((left, top, right, bottom))
    red, green, _ = cropped.split()
    redness = ImageChops.subtract(red, green).point(lambda v: 255 if v > 60 else 0)
    return redness.getbbox() is not None


def _redness_extent_within(
    png_bytes: bytes, rect: NormalizedRect, *, margin: float = 0.05
) -> tuple[int, int]:
    """``(pixel_width, pixel_height)`` of the reddish bounding box found
    within ``rect`` -- for asserting a mark's *shape*, e.g. that a
    horizontal underline actually measures wide and short, not tall and
    narrow (P2 review: an unrotated line drawn on a rotated page comes out
    the wrong way around)."""
    with Image.open(BytesIO(png_bytes)) as image:
        rgb = image.convert("RGB")
    width, height = rgb.size
    left = max(0, int((rect.x - margin) * width))
    top = max(0, int((rect.y - margin) * height))
    right = min(width, int((rect.x + rect.width + margin) * width))
    bottom = min(height, int((rect.y + rect.height + margin) * height))
    cropped = rgb.crop((left, top, right, bottom))
    red, green, _ = cropped.split()
    redness = ImageChops.subtract(red, green).point(lambda v: 255 if v > 60 else 0)
    bbox = redness.getbbox()
    if bbox is None:
        raise AssertionError("no reddish pixels found within the target rect")
    bleft, btop, bright, bbottom = bbox
    return bright - bleft, bbottom - btop


@pytest.fixture(autouse=True)
def _reset_font_cache() -> Iterator[None]:
    """Every test starts and ends with a clean font-registration cache, so a
    test that forces `JapaneseFontNotFoundError` (below) never leaves a
    later test unable to find the real font again."""
    engine_module._ensure_japanese_font_registered.cache_clear()
    yield
    engine_module._ensure_japanese_font_registered.cache_clear()


@pytest.mark.parametrize(
    "kind",
    [
        AnnotationKind.CIRCLE,
        AnnotationKind.CROSS,
        AnnotationKind.TRIANGLE,
        AnnotationKind.UNDERLINE,
        AnnotationKind.BOX,
    ],
)
def test_each_shape_kind_draws_within_its_target_rect(kind: AnnotationKind, tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_pdf(source)
    destination = tmp_path / "out.pdf"
    rect = NormalizedRect(x=0.3, y=0.3, width=0.2, height=0.1)

    engine = PdfiumPypdfEngine()
    engine.render_annotations(source, destination, {0: [AnnotationMark(kind=kind, rect=rect)]})

    assert engine.page_count(destination) == 1
    png = engine.render_page_png(destination, 0, scale=2.0)
    assert _has_red_within(png, rect), f"{kind} mark not found within its target rect"


def test_source_pdf_is_never_modified(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_pdf(source)
    original_bytes = source.read_bytes()
    destination = tmp_path / "out.pdf"

    engine = PdfiumPypdfEngine()
    engine.render_annotations(
        source,
        destination,
        {
            0: [
                AnnotationMark(
                    kind=AnnotationKind.CIRCLE,
                    rect=NormalizedRect(x=0.1, y=0.1, width=0.1, height=0.1),
                )
            ]
        },
    )

    assert source.read_bytes() == original_bytes


def test_score_and_long_japanese_comment_text_render_within_their_rects(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_pdf(source)
    destination = tmp_path / "out.pdf"
    score_rect = NormalizedRect(x=0.8, y=0.0, width=0.18, height=0.06)
    comment_rect = NormalizedRect(x=0.05, y=0.85, width=0.9, height=0.12)
    # Close to MAX_COMMENT_CHARS (120 zenkaku chars, business-rules-and-
    # evaluation-data.md §2 (6)) so wrapping onto multiple lines is exercised.
    long_comment = (
        "この設問は根拠の説明が不十分であり、模範解答と比較すると論理の飛躍が見られます。" * 2
    )

    engine = PdfiumPypdfEngine()
    engine.render_annotations(
        source,
        destination,
        {
            0: [
                AnnotationMark(kind=AnnotationKind.SCORE, rect=score_rect, text="4/5"),
                AnnotationMark(kind=AnnotationKind.COMMENT, rect=comment_rect, text=long_comment),
            ]
        },
    )

    png = engine.render_page_png(destination, 0, scale=2.0)
    assert _has_red_within(png, score_rect)
    assert _has_red_within(png, comment_rect)
    # Reparsable -- Issue #23 acceptance: "出力PDFを再読込できる".
    reread = PdfReader(str(destination))
    assert len(reread.pages) == 1


def test_marks_land_only_on_their_own_page_in_a_multi_page_document(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_pdf(source, pages=2)
    destination = tmp_path / "out.pdf"
    rect = NormalizedRect(x=0.4, y=0.4, width=0.2, height=0.1)

    engine = PdfiumPypdfEngine()
    engine.render_annotations(
        source, destination, {1: [AnnotationMark(kind=AnnotationKind.BOX, rect=rect)]}
    )

    assert engine.page_count(destination) == 2
    first_page_png = engine.render_page_png(destination, 0, scale=2.0)
    second_page_png = engine.render_page_png(destination, 1, scale=2.0)
    assert _redness_bbox(first_page_png) is None
    assert _has_red_within(second_page_png, rect)


def test_a_mark_still_lands_correctly_on_a_rotated_page(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_pdf(source, rotation=90)
    destination = tmp_path / "out.pdf"
    rect = NormalizedRect(x=0.1, y=0.1, width=0.15, height=0.1)

    engine = PdfiumPypdfEngine()
    engine.render_annotations(
        source, destination, {0: [AnnotationMark(kind=AnnotationKind.CIRCLE, rect=rect)]}
    )

    png = engine.render_page_png(destination, 0, scale=2.0)
    assert _has_red_within(png, rect)


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_an_underline_stays_horizontal_as_displayed_on_a_rotated_page(
    rotation: int, tmp_path: Path
) -> None:
    """A circle (the only shape the pre-existing rotated-page test used)
    can't reveal a directional-content bug -- it looks the same rotated or
    not. An underline can: it must render wide and short (spanning the
    rect's displayed width, hugging its displayed bottom edge), never tall
    and narrow, on every page rotation (P2 review)."""
    source = tmp_path / "source.pdf"
    _write_pdf(source, rotation=rotation)
    destination = tmp_path / "out.pdf"
    # Wide, short rect, as an underline beneath a line of text would be.
    rect = NormalizedRect(x=0.2, y=0.4, width=0.5, height=0.04)

    engine = PdfiumPypdfEngine()
    engine.render_annotations(
        source, destination, {0: [AnnotationMark(kind=AnnotationKind.UNDERLINE, rect=rect)]}
    )

    png = engine.render_page_png(destination, 0, scale=2.0)
    pixel_width, pixel_height = _redness_extent_within(png, rect)
    assert pixel_width > pixel_height * 3, (
        f"expected a wide, short line (width={pixel_width}px, height={pixel_height}px)"
    )


def test_a_mark_lands_correctly_on_a_page_with_a_non_zero_mediabox_origin(tmp_path: Path) -> None:
    """Regression test for P2 review: an earlier version of `render_annotations`
    shifted every mark's coordinates by the page's own MediaBox origin before
    merging, which is backwards for `merge_page` (it composites the overlay's
    content stream using absolute coordinates, with no transform of its own)
    -- every mark landed offset by the MediaBox origin on any page whose
    MediaBox does not start at ``(0, 0)`` (PoC 3's own
    ``a4-mediabox-offset`` fixture is exactly this case)."""
    source = tmp_path / "source.pdf"
    _write_pdf_with_mediabox_offset(source, offset=(100.0, 200.0))
    destination = tmp_path / "out.pdf"
    rect = NormalizedRect(x=0.3, y=0.3, width=0.2, height=0.1)

    engine = PdfiumPypdfEngine()
    engine.render_annotations(
        source, destination, {0: [AnnotationMark(kind=AnnotationKind.BOX, rect=rect)]}
    )

    png = engine.render_page_png(destination, 0, scale=2.0)
    assert _has_red_within(png, rect)


def test_a_page_with_no_marks_is_left_untouched(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_pdf(source, pages=2)
    destination = tmp_path / "out.pdf"

    engine = PdfiumPypdfEngine()
    engine.render_annotations(source, destination, {})

    assert engine.page_count(destination) == 2
    for page_index in range(2):
        png = engine.render_page_png(destination, page_index, scale=1.5)
        assert _redness_bbox(png) is None


def test_missing_japanese_font_fails_clearly_when_a_comment_is_drawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        engine_module,
        "_JAPANESE_FONT_CANDIDATES",
        (tmp_path / "does-not-exist.ttc",),
    )
    source = tmp_path / "source.pdf"
    _write_pdf(source)
    destination = tmp_path / "out.pdf"

    engine = PdfiumPypdfEngine()
    with pytest.raises(JapaneseFontNotFoundError):
        engine.render_annotations(
            source,
            destination,
            {
                0: [
                    AnnotationMark(
                        kind=AnnotationKind.COMMENT,
                        rect=NormalizedRect(x=0.1, y=0.1, width=0.5, height=0.1),
                        text="コメント",
                    )
                ]
            },
        )
    # A failed render must not leave a partial output file behind for the
    # caller to mistake for a real one.
    assert not destination.exists()


def test_missing_japanese_font_does_not_affect_pure_shape_marks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        engine_module,
        "_JAPANESE_FONT_CANDIDATES",
        (tmp_path / "does-not-exist.ttc",),
    )
    source = tmp_path / "source.pdf"
    _write_pdf(source)
    destination = tmp_path / "out.pdf"
    rect = NormalizedRect(x=0.3, y=0.3, width=0.2, height=0.1)

    engine = PdfiumPypdfEngine()
    engine.render_annotations(
        source, destination, {0: [AnnotationMark(kind=AnnotationKind.CIRCLE, rect=rect)]}
    )

    png = engine.render_page_png(destination, 0, scale=2.0)
    assert _has_red_within(png, rect)
