"""``PdfEngine`` backed by pypdfium2 (rasterize) and pypdf (overlay / stamp).

Selected by PoC 3 (GitHub issue #12) as the licence-clean alternative to
PyMuPDF. Both libraries are permissively licensed (pypdfium2: Apache-2.0 /
BSD-3-Clause; pypdf: BSD-3-Clause) and need no commercial agreement.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from auto_scoring.domain.models import AnnotationKind
from auto_scoring.domain.pdf_engine import AnnotationMark
from auto_scoring.domain.pdf_geometry import (
    NormalizedPoint,
    PageGeometry,
    UserSpacePoint,
    normalized_to_user_space,
)

#: Windows-shipped Japanese fonts, tried in this order (Issue #23). The MVP
#: targets Windows only (simplified-design-spec.md §3.1; CI runs on
#: `windows-latest`, docs/quality-gates.md), so relying on the OS's own
#: fonts avoids bundling and redistributing a font file -- see
#: docs/pdf-export.md "日本語フォントの解決" for the tradeoff (cross-platform
#: font bundling is an open item for a later, non-Windows issue).
_JAPANESE_FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\YuGothM.ttc"),
    Path(r"C:\Windows\Fonts\meiryo.ttc"),
    Path(r"C:\Windows\Fonts\msgothic.ttc"),
    Path(r"C:\Windows\Fonts\msmincho.ttc"),
)
_JAPANESE_FONT_NAME = "AutoScoringJPFont"

#: Comment/score text color -- a dark red, distinct from the pure-red shape
#: marks (`_MARK_RGB`) so annotated text stays legible against them.
_TEXT_RGB = (0.55, 0.0, 0.0)
_MARK_RGB = (1.0, 0.0, 0.0)
_MIN_FONT_SIZE_PT = 6.0
_MAX_FONT_SIZE_PT = 14.0
_LINE_HEIGHT_FACTOR = 1.2


class JapaneseFontNotFoundError(RuntimeError):
    """No candidate in `_JAPANESE_FONT_CANDIDATES` exists on this machine.

    Raised instead of letting reportlab fail on a missing file with a less
    actionable error -- see docs/pdf-export.md.
    """

    def __init__(self) -> None:
        candidates = ", ".join(str(path) for path in _JAPANESE_FONT_CANDIDATES)
        super().__init__(
            "no Japanese-capable font found for PDF export annotation comments; "
            f"tried: {candidates} (docs/pdf-export.md)"
        )


@lru_cache(maxsize=1)
def _ensure_japanese_font_registered() -> str:
    """Register the first available candidate font with reportlab, once per
    process, and return its registered name. Not cached on failure
    (`lru_cache` does not memoize a raised exception), so a later retry can
    still succeed if the environment changes.
    """
    for candidate in _JAPANESE_FONT_CANDIDATES:
        if candidate.exists():
            pdfmetrics.registerFont(TTFont(_JAPANESE_FONT_NAME, str(candidate), subfontIndex=0))
            return _JAPANESE_FONT_NAME
    raise JapaneseFontNotFoundError()


class PdfiumPypdfEngine:
    """Concrete :class:`~auto_scoring.domain.pdf_engine.PdfEngine`."""

    def page_count(self, source: Path) -> int:
        reader = PdfReader(str(source))
        return len(reader.pages)

    def is_encrypted(self, source: Path) -> bool:
        reader = PdfReader(str(source))
        return reader.is_encrypted

    def page_geometry(self, source: Path, page_index: int) -> PageGeometry:
        reader = PdfReader(str(source))
        page = reader.pages[page_index]
        media, crop = page.mediabox, page.cropbox
        # pdfium displays CropBox intersected with MediaBox.
        left = max(float(crop.left), float(media.left))
        bottom = max(float(crop.bottom), float(media.bottom))
        right = min(float(crop.right), float(media.right))
        top = min(float(crop.top), float(media.top))
        return PageGeometry(
            crop_width=right - left,
            crop_height=top - bottom,
            crop_offset_x=left,
            crop_offset_y=bottom,
            rotation=int(page.rotation),
        )

    def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
        document = pdfium.PdfDocument(str(source))
        try:
            image = document[page_index].render(scale=scale).to_pil()
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
        finally:
            document.close()

    def stamp_markers(
        self,
        source: Path,
        destination: Path,
        markers: Mapping[int, Sequence[NormalizedPoint]],
        *,
        mark_size_pt: float = 8.0,
    ) -> None:
        writer = PdfWriter()
        writer.append(PdfReader(str(source)))
        for page_index, points in markers.items():
            geometry = self.page_geometry(source, page_index)
            page = writer.pages[page_index]
            content = "\n".join(
                _filled_square(normalized_to_user_space(point, geometry), mark_size_pt)
                for point in points
            )
            overlay = PdfReader(BytesIO(_overlay_pdf(page, content))).pages[0]
            page.merge_page(overlay)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            writer.write(handle)

    def render_annotations(
        self,
        source: Path,
        destination: Path,
        marks: Mapping[int, Sequence[AnnotationMark]],
        note_pages: Sequence[Sequence[AnnotationMark]] = (),
    ) -> None:
        writer = PdfWriter()
        writer.append(PdfReader(str(source)))
        for page_index, page_marks in marks.items():
            if not page_marks:
                continue
            geometry = self.page_geometry(source, page_index)
            page = writer.pages[page_index]
            overlay_bytes = _render_annotation_overlay(page.mediabox, page_marks, geometry)
            overlay = PdfReader(BytesIO(overlay_bytes)).pages[0]
            page.merge_page(overlay)
        if note_pages:
            first = self.page_geometry(source, 0)
            for page_marks in note_pages:
                writer.append(PdfReader(BytesIO(_render_note_page(page_marks, first))))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            writer.write(handle)


def _render_note_page(marks: Sequence[AnnotationMark], source_first_page: PageGeometry) -> bytes:
    """A fresh one-page PDF carrying ``marks`` -- the appended note page
    Issue #161 writes annotation notes onto.

    Unlike `_render_annotation_overlay` this is a *new* page rather than an
    overlay merged onto an existing one, so there is no MediaBox origin and
    no ``/Rotate`` to reconcile: the page is created at the source's first
    page's **displayed** size (`PageGeometry.displayed_width`/
    ``displayed_height``, i.e. after any quarter turn), with a zero origin
    and no rotation of its own. Sizing it from the answer sheet rather than
    from a fixed A4 is what keeps the printed result one uniform stack of
    paper: a landscape answer gets landscape notes.

    ``marks`` are page-normalized against that same displayed page, which is
    what `_draw_mark_in_place` already expects, so the geometry handed to it
    describes this new page and nothing about the source's own boxes.
    """
    width = source_first_page.displayed_width
    height = source_first_page.displayed_height
    geometry = PageGeometry(crop_width=width, crop_height=height)
    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=(width, height))
    for mark in marks:
        _draw_mark_in_place(pdf_canvas, mark, geometry)
    pdf_canvas.save()
    return buffer.getvalue()


def _render_annotation_overlay(
    mediabox: RectangleObject, marks: Sequence[AnnotationMark], geometry: PageGeometry
) -> bytes:
    """A one-page PDF with ``marks`` drawn via reportlab -- merged onto the
    real page by `render_annotations`.

    Every drawing operator this function emits already carries the correct
    **absolute** PDF user-space coordinate -- the same one `stamp_markers`'s
    `_filled_square`/`_overlay_pdf` pair uses (P2 review, round 1: an
    earlier version of this function shifted coordinates by the page's own
    MediaBox origin, which is backwards -- content needs absolute
    coordinates, not ones relative to that origin).

    That alone is not sufficient, though: ``pypdf``'s ``merge_page`` clips
    the merged content to the *overlay's own* page box (P2 review, round 2)
    -- and reportlab's `Canvas` always declares its generated page's
    ``/MediaBox`` starting at ``(0, 0)``, sized only ``pagesize`` (here,
    just the target's *width*/*height*, not its actual absolute range). On
    a page whose real MediaBox does not start at ``(0, 0)`` (PoC 3's
    ``a4-mediabox-offset``/``a4-cropbox-inset`` fixtures), a mark's real
    absolute coordinates can fall entirely outside that zero-origin box --
    e.g. a target box ``[100, 200, 700, 1000]`` (width 600, height 800)
    makes the overlay's own box ``[0, 0, 600, 800]``, silently clipping
    away any mark whose absolute x exceeds 600 or y exceeds 800, even
    though both are well within the real, target page. Rewriting the
    overlay's own MediaBox/CropBox to that same absolute range below, after
    reportlab has finished writing but before `render_annotations` merges
    it, keeps the overlay's own clip boundary consistent with the absolute
    coordinates its content stream actually uses.
    """
    left, bottom = float(mediabox.left), float(mediabox.bottom)
    right, top = float(mediabox.right), float(mediabox.top)
    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=(right - left, top - bottom))
    for mark in marks:
        _draw_mark_in_place(pdf_canvas, mark, geometry)
    pdf_canvas.save()
    return _with_absolute_page_box(buffer.getvalue(), left, bottom, right, top)


def _with_absolute_page_box(
    overlay_pdf_bytes: bytes, left: float, bottom: float, right: float, top: float
) -> bytes:
    """Rewrite a one-page PDF's MediaBox *and* CropBox to
    ``[left, bottom, right, top]`` -- see `_render_annotation_overlay`'s
    docstring for why both need to match the target page's own absolute
    box, not the zero-origin one reportlab always writes.
    """
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(overlay_pdf_bytes)))
    box = RectangleObject((left, bottom, right, top))
    page = writer.pages[0]
    page.mediabox = box
    page.cropbox = box
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _draw_mark_in_place(
    pdf_canvas: canvas.Canvas, mark: AnnotationMark, geometry: PageGeometry
) -> None:
    """Draw ``mark`` at its correct absolute position *and* orientation.

    A rotated page (``/Rotate``) is a *display-time* transform: content
    drawn in user space is rotated by the viewer, not by anything this
    function does. `normalized_to_user_space` already accounts for that
    correctly for a single *point* (PoC 3), but a naive port that only maps
    the mark rect's two opposite corners and then draws an axis-aligned
    shape/text between them (an earlier version of this function) only gets
    the rect's *position and extent* right -- the *content*'s orientation
    (an upright triangle, a horizontal underline, left-to-right text) stays
    unrotated, so on a 90/270-degree page every directional mark comes out
    sideways (P2 review; a circle -- rotation-symmetric -- can't reveal this,
    which is why the existing rotated-page test missed it).

    Fixed by mapping the rect's top-left/top-right/bottom-left corners
    (not just two opposite ones) into user space: the vector from top-left
    to top-right gives both the real width in points *and* the rotation
    angle to counter-rotate the canvas by, and the vector to bottom-left
    gives the real height. `canvas.translate`/`canvas.rotate` then let every
    shape/text primitive keep being written in a simple, unrotated local
    frame (identical to what this module drew before this fix) -- origin at
    the rect's displayed top-left corner, local +x toward its displayed
    right edge, local +y toward its displayed top edge -- while the
    rotation is applied once, geometrically, instead of needing every
    primitive to know about it.
    """
    top_left = normalized_to_user_space(NormalizedPoint(mark.rect.x, mark.rect.y), geometry)
    top_right = normalized_to_user_space(
        NormalizedPoint(mark.rect.x + mark.rect.width, mark.rect.y), geometry
    )
    bottom_left = normalized_to_user_space(
        NormalizedPoint(mark.rect.x, mark.rect.y + mark.rect.height), geometry
    )
    width_pt = math.hypot(top_right.x - top_left.x, top_right.y - top_left.y)
    height_pt = math.hypot(bottom_left.x - top_left.x, bottom_left.y - top_left.y)
    angle_deg = math.degrees(math.atan2(top_right.y - top_left.y, top_right.x - top_left.x))

    pdf_canvas.saveState()
    pdf_canvas.translate(top_left.x, top_left.y)
    pdf_canvas.rotate(angle_deg)
    _draw_mark(pdf_canvas, mark, 0.0, -height_pt, width_pt, 0.0)
    pdf_canvas.restoreState()


_SHAPE_KINDS_NEEDING_TEXT = frozenset({AnnotationKind.SCORE, AnnotationKind.COMMENT})


def _draw_mark(
    pdf_canvas: canvas.Canvas, mark: AnnotationMark, x0: float, y0: float, x1: float, y1: float
) -> None:
    if mark.kind in _SHAPE_KINDS_NEEDING_TEXT:
        _draw_text(pdf_canvas, mark.text or "", x0, y0, x1, y1)
        return
    pdf_canvas.setStrokeColorRGB(*_MARK_RGB)
    pdf_canvas.setLineWidth(max(1.0, (x1 - x0) * 0.04))
    if mark.kind is AnnotationKind.CIRCLE:
        pdf_canvas.ellipse(x0, y0, x1, y1, stroke=1, fill=0)
    elif mark.kind is AnnotationKind.CROSS:
        pdf_canvas.line(x0, y0, x1, y1)
        pdf_canvas.line(x0, y1, x1, y0)
    elif mark.kind is AnnotationKind.TRIANGLE:
        path = pdf_canvas.beginPath()
        path.moveTo((x0 + x1) / 2.0, y1)
        path.lineTo(x1, y0)
        path.lineTo(x0, y0)
        path.close()
        pdf_canvas.drawPath(path, stroke=1, fill=0)
    elif mark.kind is AnnotationKind.UNDERLINE:
        pdf_canvas.line(x0, y0, x1, y0)
    elif mark.kind is AnnotationKind.BOX:
        pdf_canvas.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0)


#: Marks the last drawn line as cut off when even `_MIN_FONT_SIZE_PT` can't
#: fit every wrapped line inside the mark's rect (P2 review).
_ELLIPSIS = "…"


def _draw_text(
    pdf_canvas: canvas.Canvas, text: str, x0: float, y0: float, x1: float, y1: float
) -> None:
    if not text:
        return
    font_name = _ensure_japanese_font_registered()
    width = max(x1 - x0, 1.0)
    height = max(y1 - y0, 1.0)
    font_size = min(_MAX_FONT_SIZE_PT, max(_MIN_FONT_SIZE_PT, height))
    lines = _wrap_text(pdf_canvas, text, font_name, font_size, width)
    while font_size > _MIN_FONT_SIZE_PT and len(lines) * font_size * _LINE_HEIGHT_FACTOR > height:
        font_size -= 1.0
        lines = _wrap_text(pdf_canvas, text, font_name, font_size, width)
    # Even at `_MIN_FONT_SIZE_PT`, `lines` may still be too many to fit
    # `height`. Rather than let the remaining lines pile onto the same
    # baseline (`max(y, y0)`, an earlier version of this function -- P2
    # review: illegible overlapping text on any long comment against a
    # small registered comment area), show only as many as actually fit and
    # mark the cut with an ellipsis -- an explicit, honest overflow policy.
    max_lines = max(1, int(height / (font_size * _LINE_HEIGHT_FACTOR)))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _truncate_with_ellipsis(pdf_canvas, lines[-1], font_name, font_size, width)
    pdf_canvas.setFillColorRGB(*_TEXT_RGB)
    pdf_canvas.setFont(font_name, font_size)
    y = y1 - font_size
    for line in lines:
        pdf_canvas.drawString(x0, y, line)
        y -= font_size * _LINE_HEIGHT_FACTOR


def _truncate_with_ellipsis(
    pdf_canvas: canvas.Canvas, line: str, font_name: str, font_size: float, max_width: float
) -> str:
    if pdf_canvas.stringWidth(line + _ELLIPSIS, font_name, font_size) <= max_width:
        return line + _ELLIPSIS
    truncated = line
    while truncated and (
        pdf_canvas.stringWidth(truncated + _ELLIPSIS, font_name, font_size) > max_width
    ):
        truncated = truncated[:-1]
    return truncated + _ELLIPSIS


def _wrap_text(
    pdf_canvas: canvas.Canvas, text: str, font_name: str, font_size: float, max_width: float
) -> list[str]:
    """Greedy character-by-character wrap (not word-by-word: Japanese text
    has no spaces to break on)."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for char in paragraph:
            candidate = current + char
            if current and pdf_canvas.stringWidth(candidate, font_name, font_size) > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)
    return lines


def _filled_square(center: UserSpacePoint, size_pt: float) -> str:
    """A PDF content-stream op set: a red square of ``size_pt`` centred on ``center``."""
    x = center.x - size_pt / 2.0
    y = center.y - size_pt / 2.0
    return f"q 1 0 0 rg {x:.4f} {y:.4f} {size_pt:.4f} {size_pt:.4f} re f Q"


def _overlay_pdf(reference_page: PageObject, content: str) -> bytes:
    """A one-page PDF sized like ``reference_page`` that draws ``content``.

    Used as a pypdf overlay: ``merge_page`` concatenates its content stream onto
    the target page in the same user-space coordinates.
    """
    box = reference_page.mediabox
    left = float(box.left)
    bottom = float(box.bottom)
    right = float(box.right)
    top = float(box.top)
    body = content.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox "
            f"[{left:.4f} {bottom:.4f} {right:.4f} {top:.4f}] "
            f"/Contents 4 0 R >>"
        ).encode("latin-1"),
        b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    startxref = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    out += b"startxref\n%d\n%%%%EOF" % startxref
    return bytes(out)
