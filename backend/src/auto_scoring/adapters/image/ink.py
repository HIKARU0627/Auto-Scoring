"""Measuring the ink on a rendered page: where the long printed rules run,
and how much ink a crop has at all (Issue #122).

Both answers come from the *same* raster the answer-area crop is taken from
(``PdfEngine.render_page_png`` at ``adapters.submission_intake.RENDER_SCALE``)
and share one definition of "ink", which is the reason they live in one
module rather than two.

Neither function reads or reports anything about *what* is written -- only
positions and a coverage ratio. The pages are a cram school's copyrighted
material (AGENTS.md "Security"), and nothing here may end up describing them.
"""

from __future__ import annotations

import cv2
import numpy as np

from auto_scoring.domain.answer_area_snapping import PageRuling

#: Grayscale level at or below which a pixel counts as ink.
#:
#: These are scans, not synthetic pages: 200 (of 255) keeps a faint printed
#: rule while leaving paper texture out. Measured on three real answer
#: sheets, a region of blank paper comes out at a coverage of 0.000015 or
#: less at this level, against 0.050-0.121 for a region a student wrote in --
#: four orders of magnitude apart, which is what makes
#: `domain.submission_intake.NEARLY_BLANK_INK_COVERAGE` safe to set.
_INK_LEVEL = 200

#: How long an unbroken run of ink must be, as a fraction of the page
#: dimension it runs along, before the morphological opening keeps it. Below
#: this, handwriting strokes and the vertical strokes of printed characters
#: survive and are reported as ruling.
_MIN_RUN = 0.035

#: How much of the page dimension a rule must span in total to be reported.
#: A rule bounding one answer column runs a fraction of the page, not all of
#: it, so this is well under half.
_MIN_SPAN = 0.10

#: Columns/rows this close together are one rule, not two -- a rule is a few
#: pixels wide at any useful render scale, and an antialiased edge widens it.
_MERGE_GAP = 0.003


def measure_page_ruling(png_bytes: bytes) -> PageRuling:
    """The normalized positions of the long printed rules on one page raster.

    A rule is reported at the *midpoint* of the run of columns (or rows) it
    covers, so a 3-pixel-wide printed line yields one position rather than
    three. Returns empty tuples for a page with no ruling at all, which is a
    normal sheet, not a failure -- see `PageRuling`.
    """
    image = _decode(png_bytes)
    height, width = int(image.shape[0]), int(image.shape[1])
    ink = (image <= _INK_LEVEL).astype(np.uint8)
    return PageRuling(
        vertical=_lines(ink, axis=0, along=height, across=width),
        horizontal=_lines(ink, axis=1, along=width, across=height),
    )


def ink_coverage(png_bytes: bytes) -> float:
    """The fraction of ``png_bytes`` that is ink, ``0.0``-``1.0``.

    Used by intake to tell a crop that landed on the answer from one that
    landed on the margin (`domain.submission_intake.is_nearly_blank_crop`).
    """
    image = _decode(png_bytes)
    return float((image <= _INK_LEVEL).mean())


def _decode(png_bytes: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("could not decode page image")
    return image


def _lines(ink: np.ndarray, *, axis: int, along: int, across: int) -> tuple[float, ...]:
    """Positions (normalized against ``across``) of the rules running along
    ``axis``.

    ``axis=0`` sums down columns and so finds *vertical* rules; ``axis=1``
    finds horizontal ones. The morphological opening before the sum is what
    separates a rule from a column of unrelated ink that happens to line up:
    only runs at least ``_MIN_RUN`` of ``along`` long survive it.
    """
    run = max(3, int(_MIN_RUN * along))
    kernel_size = (1, run) if axis == 0 else (run, 1)
    kept = cv2.morphologyEx(
        ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, kernel_size)
    )
    totals = kept.sum(axis=axis)
    hits = np.nonzero(totals > _MIN_SPAN * along)[0]
    if hits.size == 0:
        return ()
    gap = max(1, int(_MERGE_GAP * across))
    positions: list[float] = []
    start = previous = int(hits[0])
    for index in hits[1:]:
        current = int(index)
        if current - previous > gap:
            positions.append((start + previous) / 2.0 / across)
            start = current
        previous = current
    positions.append((start + previous) / 2.0 / across)
    return tuple(positions)
