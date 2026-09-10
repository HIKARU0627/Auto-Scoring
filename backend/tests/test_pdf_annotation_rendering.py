"""Integration tests for `PdfiumPypdfEngine.render_annotations` (Issue #23).

Real pypdf + pdfium, same "stamp then rasterize and measure red pixels"
methodology PoC 3's own `test_pdf_engine_roundtrip.py` established -- these
extend it to the richer marks (circle/cross/triangle/underline/box/score/
comment) Issue #23 adds, including Japanese comment text, multi-page
placement, rotation, and a missing-font failure.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject, RectangleObject

import auto_scoring.adapters.pdf.pdfium_pypdf_engine as engine_module
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import (
    _ELLIPSIS,
    JapaneseFontNotFoundError,
    PdfiumPypdfEngine,
)
from auto_scoring.domain.models import MAX_COMMENT_CHARS, AnnotationKind, NormalizedRect
from auto_scoring.domain.pdf_engine import AnnotationMark
from auto_scoring.domain.pdf_export import (
    _NOTE_PAGE_FONT_SIZE_PT,
    NoteEntry,
    build_note_pages,
    note_page_heading,
)
from tests.font_support import install_font_covering
from tests.pdf_content import drawn_font_sizes, drawn_text
from tests.pdf_ink import has_red_within, redness_bbox

_A4_W, _A4_H = 595.0, 842.0

#: A mark rect well inside the page, for tests whose subject is the note
#: page rather than where an answer-sheet mark lands.
_RECT = NormalizedRect(x=0.3, y=0.3, width=0.2, height=0.1)


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
    assert has_red_within(png, rect), f"{kind} mark not found within its target rect"


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


def test_score_and_long_japanese_comment_text_render_within_their_rects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both marks are asserted to have drawn, so both sets of glyphs are
    genuinely required -- which is why this one test still skips on a Linux
    machine carrying only the split-coverage fallbacks
    (docs/mvp-acceptance.md section 4)."""
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

    install_font_covering(monkeypatch, "4/5" + long_comment)

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
    assert has_red_within(png, score_rect)
    assert has_red_within(png, comment_rect)
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
    assert redness_bbox(first_page_png) is None
    assert has_red_within(second_page_png, rect)


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
    assert has_red_within(png, rect)


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
    """Regression test for P2 review (both rounds): an earlier version of
    `render_annotations` shifted every mark's coordinates by the page's own
    MediaBox origin before merging, which is backwards -- `merge_page`
    composites the overlay's content stream using absolute coordinates, with
    no transform of its own (round 1). Fixing only that left a second bug:
    ``pypdf``'s ``merge_page`` also clips the merged content to the
    *overlay's own* page box, and reportlab always writes that box starting
    at ``(0, 0)`` -- so a mark near the *far* edge of a non-zero-origin
    MediaBox (this fixture's real box is ``[100, 200, 695, 1042]``) still
    got clipped away even with absolute coordinates, because its absolute
    position exceeds the zero-origin overlay's own width/height (round 2).
    A mark near the page's *center* (an earlier version of this test) can't
    reveal that second bug -- centered coordinates happen to stay inside the
    zero-origin box's bounds by coincidence."""
    source = tmp_path / "source.pdf"
    _write_pdf_with_mediabox_offset(source, offset=(100.0, 200.0))
    destination = tmp_path / "out.pdf"
    # Near the top-right corner as displayed -- its absolute coordinates
    # exceed the target box's own width/height (595x842), which is exactly
    # what a zero-origin overlay box of that same size would clip away.
    rect = NormalizedRect(x=0.85, y=0.05, width=0.1, height=0.1)

    engine = PdfiumPypdfEngine()
    engine.render_annotations(
        source, destination, {0: [AnnotationMark(kind=AnnotationKind.BOX, rect=rect)]}
    )

    png = engine.render_page_png(destination, 0, scale=2.0)
    assert has_red_within(png, rect)


def test_a_page_with_no_marks_is_left_untouched(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_pdf(source, pages=2)
    destination = tmp_path / "out.pdf"

    engine = PdfiumPypdfEngine()
    engine.render_annotations(source, destination, {})

    assert engine.page_count(destination) == 2
    for page_index in range(2):
        png = engine.render_page_png(destination, page_index, scale=1.5)
        assert redness_bbox(png) is None


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
    assert has_red_within(png, rect)


# --------------------------------------------------------------------------- #
# Appended note pages (Issue #161)
# --------------------------------------------------------------------------- #


def _note_page_for(text: str) -> tuple[AnnotationMark, ...]:
    """One note page's worth of marks, laid out by the domain itself, so
    this file tests the engine against the geometry production really hands
    it rather than against a rect invented here."""
    return build_note_pages(
        [NoteEntry(page=1, question_number="問1", text=text)],
        heading=note_page_heading(test_name="日本史添削", submission_id="sub-1"),
        page_width_pt=_A4_W,
        page_height_pt=_A4_H,
    )[0]


def test_note_pages_are_appended_after_the_answer_and_carry_the_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #161's whole point, in one assertion pair: the sentence is on
    the appended sheet **and** it is not on the answer sheet.

    Both halves are needed. "The note is not on the answer" alone passes
    just as well when the export drew nothing anywhere, which is the state
    Issue #141 was filed about.
    """
    note = "理由の説明が不足しています。"
    install_font_covering(monkeypatch, note + "第頁問日本史添削")
    source = tmp_path / "source.pdf"
    _write_pdf(source)
    destination = tmp_path / "out.pdf"

    engine = PdfiumPypdfEngine()
    engine.render_annotations(
        source,
        destination,
        {0: [AnnotationMark(kind=AnnotationKind.CROSS, rect=_RECT)]},
        [_note_page_for(note)],
    )

    assert engine.page_count(destination) == 2, "the note page was not appended"
    assert note in drawn_text(destination, 1)
    assert note not in drawn_text(destination, 0), "prose was drawn over the answer"


def test_the_answer_page_keeps_its_own_size_and_the_note_page_matches_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A note page that came out A4 behind a landscape answer is two
    different sheets of paper in one stapled bundle."""
    install_font_covering(monkeypatch, "第頁問日本史添削")
    source = tmp_path / "source.pdf"
    _write_pdf(source, rotation=90)
    destination = tmp_path / "out.pdf"

    engine = PdfiumPypdfEngine()
    engine.render_annotations(source, destination, {}, [_note_page_for("コメント")])

    answer = engine.page_geometry(destination, 0)
    notes = engine.page_geometry(destination, 1)
    assert (notes.displayed_width, notes.displayed_height) == (
        answer.displayed_width,
        answer.displayed_height,
    )


def test_a_note_is_drawn_at_a_size_a_student_can_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_draw_text` shrinks a point at a time down to a 6pt floor and then
    truncates with an ellipsis. Neither may happen to a note: the domain
    sizes every rect so that the descent stops at
    `domain.pdf_export._NOTE_PAGE_FONT_SIZE_PT`, and this reads the ``Tf``
    the content stream actually carries to prove it did.

    A comment at `models.MAX_COMMENT_CHARS` is the worst case the model
    permits, so it is the one measured.
    """
    note = "あ" * MAX_COMMENT_CHARS
    install_font_covering(monkeypatch, note + "第頁問日本史添削")
    source = tmp_path / "source.pdf"
    _write_pdf(source)
    destination = tmp_path / "out.pdf"

    engine = PdfiumPypdfEngine()
    engine.render_annotations(source, destination, {}, [_note_page_for(note)])

    sizes = drawn_font_sizes(destination, 1)
    assert sizes, "nothing was drawn on the note page at all"
    assert min(sizes) >= _NOTE_PAGE_FONT_SIZE_PT
    assert _ELLIPSIS not in drawn_text(destination, 1), "a note was cut short"


def test_no_note_pages_means_the_page_count_does_not_change(tmp_path: Path) -> None:
    """Condition on the fix: an answer with no annotation notes must not
    grow a sheet of paper. Forty answers would be forty sheets."""
    source = tmp_path / "source.pdf"
    _write_pdf(source, pages=2)
    destination = tmp_path / "out.pdf"

    engine = PdfiumPypdfEngine()
    engine.render_annotations(
        source, destination, {0: [AnnotationMark(kind=AnnotationKind.CIRCLE, rect=_RECT)]}
    )

    assert engine.page_count(destination) == 2
