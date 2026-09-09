"""Re-measuring a detected answer box against the ruling printed on the page
(Issue #122).

**Why this exists.** `adapters.answer_area_detection` asks a vision model
where each question's answer area is, and the model answers with coordinates.
Issue #122 measured what those coordinates actually are, and they are not a
measurement:

* On a synthetic sheet whose four columns sat at *unequal* spacing
  (0.220 / 0.160 / 0.300 apart), the model returned four boxes whose left
  edges were 0.3748 / 0.5320 / 0.6892 / 0.8464 -- **every gap exactly
  0.1572**. The count and the right-to-left reading order were right; the
  positions were invented.
* The reported width was 0.0605 in three independent runs across two
  different documents, while the real columns were 0.0487 and 0.0457 wide.
  A constant, not a measurement.
* Worst observed error: **0.181 of the page width**.

**Why not a constant correction.** Issue #122 originally recorded the error
as "consistently to the right, 3-4% of the page width". It is not: on a sheet
whose columns happen to sit near the model's stereotype the same call is
accurate to 0.006, and errs to the *left* as often as to the right. Anything
that subtracts a fixed offset would break the cases that currently work.
`tests/test_answer_area_snapping.py` fails if such a correction is ever added.

**What this module does instead.** The printed ruling is measurable -- to the
pixel, with plain morphology, from the same raster the crop is taken from
(`adapters.image.ink.measure_page_ruling`). So the model keeps the job it is
good at (*which question* a box belongs to) and loses the one it is not
(*where* the box is): every edge that lands near a printed rule is moved onto
it.

**What this cannot do, and why Issue #122's second half is not optional.**
Snapping repairs a near miss. It cannot repair an invention: a box the model
placed over the wrong column snaps *onto that wrong column*, confidently and
silently. `tests/test_answer_area_snapping.py` pins that as a property of
this module rather than leaving it as folklore -- it is the reason the crop
has to become something a person can look at
(`domain.submission_intake.is_nearly_blank_crop`, and the review screen).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from auto_scoring.domain.profile import NormalizedBBox

#: How far an edge may be from a printed rule and still be treated as
#: naming it, as a fraction of the page's width (x) or height (y).
#:
#: **Measured, not chosen.** Issue #122 ran the real detector over three
#: subjects' answer sheets and measured the distance from each of the 52
#: reported box edges to the nearest printed rule on the same page. The
#: distribution has an empty band exactly here:
#:
#: ===================  =====
#: distance             edges
#: ===================  =====
#: [0.000, 0.005)          8
#: [0.005, 0.010)          2
#: [0.010, 0.015)          8
#: **[0.015, 0.020)**  **0**
#: [0.020, 0.030)          5
#: [0.030, 0.050)          2
#: >= 0.050               27
#: ===================  =====
#:
#: Below the gap the model is naming a rule and missing it slightly; above
#: it, in every case examined, it is naming a place where the page has no
#: rule at all. 52 edges from 3 subjects is not a large sample and the gap
#: may be luck, so the *property* is what the tests pin (a near miss snaps,
#: an invention does not), never this number.
SNAP_TOLERANCE = 0.015


@dataclass(frozen=True)
class PageRuling:
    """Where the long printed rules run on one rendered page, normalized to
    ``0..1`` in the same top-left-origin space as `NormalizedBBox`.

    ``vertical`` holds x positions (rules that run down the page),
    ``horizontal`` holds y positions. Either may be empty: a sheet whose
    answer space is an open region under a heading has no ruling to snap to,
    and that is a normal answer, not a failure.
    """

    vertical: tuple[float, ...] = ()
    horizontal: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        for name, lines in (("vertical", self.vertical), ("horizontal", self.horizontal)):
            if any(not 0.0 <= line <= 1.0 for line in lines):
                raise ValueError(f"PageRuling.{name} positions must all be within 0..1")


@dataclass(frozen=True)
class SnappedBBox:
    """One box after snapping, plus what moving it actually did.

    ``moved`` and ``largest_shift`` exist so the reviewer can be told -- a
    box that silently jumped 0.014 across the page is exactly the kind of
    correction that has to be visible to the person who is about to trust
    it (Issue #122's second half).
    """

    bbox: NormalizedBBox
    #: Edge names (``"x0"``/``"y0"``/``"x1"``/``"y1"``) that were moved.
    moved: tuple[str, ...] = ()
    #: The largest single movement, page-normalized. ``0.0`` when nothing moved.
    largest_shift: float = 0.0


def snap_bbox_to_ruling(
    bbox: NormalizedBBox,
    ruling: PageRuling,
    *,
    tolerance: float = SNAP_TOLERANCE,
) -> SnappedBBox:
    """Move each of ``bbox``'s edges onto the nearest printed rule within
    ``tolerance``, leaving edges with no rule near them exactly where they are.

    The two edges of one axis are decided together, not independently: if
    snapping them would leave the box with zero or negative extent -- both
    edges pulled onto the *same* rule, or past each other -- **neither**
    moves. Half of a snap is a box neither the model nor the page asked for,
    and `NormalizedBBox` would reject the degenerate result anyway, turning a
    detection that merely needed correcting into a failed one.
    """
    if tolerance < 0.0:
        raise ValueError("snap tolerance must not be negative")
    x0, x1, moved_x, shift_x = _snap_axis(
        bbox.x0, bbox.x1, ruling.vertical, tolerance, ("x0", "x1")
    )
    y0, y1, moved_y, shift_y = _snap_axis(
        bbox.y0, bbox.y1, ruling.horizontal, tolerance, ("y0", "y1")
    )
    return SnappedBBox(
        bbox=NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1),
        moved=moved_x + moved_y,
        largest_shift=max(shift_x, shift_y),
    )


def _snap_axis(
    low: float,
    high: float,
    lines: Sequence[float],
    tolerance: float,
    names: tuple[str, str],
) -> tuple[float, float, tuple[str, ...], float]:
    """One axis' pair of edges. Returns the (possibly unchanged) pair, the
    names of the edges that moved, and the largest movement."""
    snapped_low = _nearest_line(low, lines, tolerance)
    snapped_high = _nearest_line(high, lines, tolerance)
    new_low = low if snapped_low is None else snapped_low
    new_high = high if snapped_high is None else snapped_high
    if new_low >= new_high:
        return low, high, (), 0.0
    moved: list[str] = []
    shift = 0.0
    for name, before, after in ((names[0], low, new_low), (names[1], high, new_high)):
        if after != before:
            moved.append(name)
            shift = max(shift, abs(after - before))
    return new_low, new_high, tuple(moved), shift


def _nearest_line(value: float, lines: Sequence[float], tolerance: float) -> float | None:
    """The rule closest to ``value``, or ``None`` when the closest one is
    further away than ``tolerance``."""
    if not lines:
        return None
    nearest = min(lines, key=lambda line: abs(line - value))
    return nearest if abs(nearest - value) <= tolerance else None
