"""Port for the PDF read / render / annotate operations the app needs.

Adopted from PoC 3 (GitHub issue #12). Implementations live in ``adapters/``;
the domain only ever sees this protocol and :mod:`auto_scoring.domain.pdf_geometry`.

PoC 3 selected **pypdfium2 + pypdf** as the implementation (see
``docs/poc-3-pdf-coordinates.md``): PyMuPDF stays out until a licence-decision
owner records approval, and the protocol keeps that swap to one adapter.

The signatures cover only what PoC 3 exercised -- read page geometry, rasterize a
page, and stamp a mark at a normalized point. The annotation feature issue will
widen ``stamp_markers`` into real ``maru`` / ``batsu`` / comment glyphs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from auto_scoring.domain.models import AnnotationKind, NormalizedRect
from auto_scoring.domain.pdf_geometry import NormalizedPoint, PageGeometry


@dataclass(frozen=True, kw_only=True)
class AnnotationMark:
    """One resolved, page-normalized annotation to draw (Issue #23).

    Produced by `domain.pdf_export.build_export_marks` -- coordinate/text
    resolution is entirely the domain's job (simplified-design-spec.md §12.1
    "AIにPDF座標を直接決めさせない"); a `PdfEngine` only ever draws exactly
    what it is told, at exactly the ``rect`` given, in the same displayed-page
    normalized space (`NormalizedPoint`) as `stamp_markers`.

    ``text`` is the label to draw for kinds that carry one: the confirmed
    score (``AnnotationKind.SCORE``) or the reviewer's comment
    (``AnnotationKind.COMMENT``); ``None`` for the pure-shape kinds (circle/
    cross/triangle/underline/box), which need no font at all.
    """

    kind: AnnotationKind
    rect: NormalizedRect
    text: str | None = None


class PdfEngine(Protocol):
    """Everything the core needs from a PDF toolkit."""

    def page_count(self, source: Path) -> int:
        """Return the number of pages in ``source``.

        Raises on a corrupted/unparseable file (Issue #17: "破損PDFを安全に
        拒否する"). Implementations translate their underlying library's parse
        error into a plain exception; callers in ``adapters`` classify it as
        :class:`auto_scoring.domain.pdf_intake.PdfCorruptedError`.
        """
        ...

    def is_encrypted(self, source: Path) -> bool:
        """Return whether ``source`` requires a password to open.

        The sidecar never prompts for a password (simplified-design-spec.md
        §26: no unnecessary data handling); an encrypted PDF is rejected at
        intake (Issue #17: "暗号化...PDFを安全に拒否する").
        """
        ...

    def page_geometry(self, source: Path, page_index: int) -> PageGeometry:
        """Return the crop box and rotation pdfium uses to display the page."""
        ...

    def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
        """Rasterize one page to PNG bytes at ``scale`` pixels per point."""
        ...

    def stamp_markers(
        self,
        source: Path,
        destination: Path,
        markers: Mapping[int, Sequence[NormalizedPoint]],
        *,
        mark_size_pt: float = 8.0,
    ) -> None:
        """Write ``source`` to ``destination`` with a mark at each normalized point.

        ``markers`` maps a 0-based page index to the points to stamp on it. The
        source file is never modified (simplified design spec sec. 35-4).
        """
        ...

    def render_annotations(
        self,
        source: Path,
        destination: Path,
        marks: Mapping[int, Sequence[AnnotationMark]],
        note_pages: Sequence[Sequence[AnnotationMark]] = (),
    ) -> None:
        """Write ``source`` to ``destination`` with each page's confirmed
        annotations drawn as real glyphs (Issue #23): a stroked circle/cross/
        triangle/underline/box for the pure-shape kinds, and Japanese-capable
        rendered text for score/comment. Unlike `stamp_markers` (a single red
        square, adopted from PoC 3 for test fixtures), this is the MVP output
        path simplified-design-spec.md §14 describes.

        ``marks`` maps a 0-based page index to the marks to draw on it, all
        already resolved to page-normalized rects (`domain.pdf_export.
        build_export_marks`). The source file is never modified (§35-4).

        ``note_pages`` are **blank pages appended after the source's own**,
        one per element, each carrying that element's marks in the same
        page-normalized space (Issue #161: `domain.pdf_export.
        build_note_pages`). They exist because the answer sheet was measured
        and has nowhere to put a sentence -- see that function. An empty
        ``note_pages`` appends nothing, so an answer with no annotation
        notes comes out with exactly the page count it went in with.
        """
        ...
