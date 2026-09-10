"""Measuring how far the *printed* ruling of one answer form moves between two
separate scans of it (Issue #130).

The product detects answer areas on one document (the answer-layout PDF) and
crops them out of another (the submitted answer PDF). Both are scans of the
same printed form, made at different times. This module measures the geometric
difference between two such scans and splits it into the three things that can
cause it -- rotation, translation, scale -- rather than reporting one lumped
"drift" number that no fix could be aimed at.

Nothing here reads or reports *what* is printed on the page: only the positions
of long printed rules, and the transform relating two sets of them. The pages
are a cram school's copyrighted material (AGENTS.md "Security").
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from auto_scoring.adapters.image.ink import measure_page_ruling

#: Grayscale level at or below which a pixel counts as ink, matching
#: `adapters.image.ink._INK_LEVEL` so the skew estimate and the ruling
#: positions are measured off the same definition.
_INK_LEVEL = 200

#: Half-width of the skew search, in degrees. A sheet-fed scanner that fed the
#: page this crookedly would be visibly jammed; anything larger is a page put
#: in sideways, which is a different problem (`/Rotate`, PoC 3).
_SKEW_SPAN = 3.0
_SKEW_COARSE_STEP = 0.25
_SKEW_FINE_STEP = 0.02

#: How far a rule may sit from where the candidate transform predicts it and
#: still count as the same rule. The answer columns on the real forms are
#: 0.045-0.09 of the page apart, so this is well under half the closest
#: spacing -- a value that let an edge match its *neighbour* would report a
#: whole column of drift that is not there.
_MATCH_TOLERANCE = 0.006

#: Largest translation considered. Past this the two pages are not the same
#: form scanned twice, they are two different pages.
_SHIFT_SPAN = 0.06

#: How many times the fit may re-pair its rules against its own latest
#: estimate. Converges in two or three on every page measured; the cap only
#: stops a pathological oscillation.
_REFINE_PASSES = 5

#: Fewest matched rules an axis needs before its fit is reported. Two points
#: determine a scale-and-shift exactly, so a two-point "fit" measures nothing;
#: four leaves two points of disagreement to show up in the residual.
MIN_MATCHED_RULES = 4

#: Why an axis has no fit. The three are different evidence: a page with no
#: ruling to speak of, a page whose ruling refuses to line up at all, and a
#: page whose ruling lines up two incompatible ways.
TOO_FEW_RULES = "fewer than four printed rules on one of the pages"
NO_ALIGNMENT = "no alignment matched enough of the ruling"
AMBIGUOUS = "two incompatible alignments explain the ruling equally well"

#: Fewest matched rules as a fraction of the rules the sparser page offers.
#: A fit that explains half the ruling has as good a claim to being a
#: coincidence as a measurement -- and a coincidence is exactly what produces
#: an impossible scale, because the few rules it happens to line up sit close
#: together and leave the slope unconstrained.
_MIN_MATCH_FRACTION = 0.6

#: How much of the page the matched rules must span before their slope is
#: reported as a scale. Rules crowded into a tenth of the page determine a
#: scale only to within ten times the tolerance.
_MIN_MATCH_SPAN = 0.30

#: Largest change of scale that two *scans* of one sheet can produce. Both
#: pages are already normalized against their own page box, so scanner DPI and
#: page size have divided out and only the paper is left; paper moves by
#: fractions of a percent with humidity and duplex printing. A percent is
#: generous.
#:
#: How many fewer rules a rival may match and still count as explaining the
#: page equally well. One, not zero: on the real corpus, zero let through the
#: single page pair whose two readings disagree in *sign* -- one said the sheet
#: had moved 0.04 left, the other that it had stretched right -- and two threw
#: away most of the densely ruled pages for nothing. The medians move by under
#: 0.0006 of the page across all three settings; only that one pair's maximum
#: moves, which is why it is excluded rather than averaged in.
_RIVAL_MARGIN = 1

#: A rival fit is one whose translation differs from the winner's by more than
#: this many match tolerances. Closer than that and it is the same answer
#: measured slightly differently, not a competing one.
_RIVAL_SEPARATION = 3.0

#: The bound is here because without it the fit does not merely become noisy,
#: it becomes wrong in a specific way: a form's header rules are a near-ladder
#: 0.013-0.026 apart, close enough to `_MATCH_TOLERANCE` that the whole ladder
#: can slide by one rung, and the only way to reconcile a slid header with an
#: unslid rule at the foot of the page is a 5% stretch. Two real page pairs did
#: exactly that. A fit that wants more than this is not measuring paper.
_MAX_SCALE_DRIFT = 0.01


@dataclass(frozen=True)
class AxisFit:
    """The scale-and-shift relating one axis' printed rules on two scans.

    ``scale``/``shift`` map page A's normalized coordinate to page B's
    (``b = scale * a + shift``). ``matched`` is the denominator behind them.
    """

    matched: int
    available_a: int
    available_b: int
    scale: float
    shift: float
    #: Largest distance from a matched rule to where the fit predicts it. What
    #: the rotation-plus-scale-plus-shift model does *not* explain.
    max_residual: float
    #: Whether ``scale`` was measured or assumed. ``False`` means the free fit
    #: asked for more stretch than `_MAX_SCALE_DRIFT` allows and was redone as
    #: a pure translation: the translation and the residual are still
    #: measurements, the scale is not.
    scale_measured: bool = True


@dataclass(frozen=True)
class PageScan:
    """One rendered page, reduced to the two things this probe compares."""

    width: int
    height: int
    skew_degrees: float
    #: Rule positions measured *after* removing ``skew_degrees``, so the two
    #: pages are compared in a common upright frame and the rotation is not
    #: smeared into the translation.
    vertical: tuple[float, ...]
    horizontal: tuple[float, ...]


@dataclass(frozen=True)
class AxisDrift:
    """One axis' share of the difference between two scans, split by cause.

    Every displacement is page-normalized -- x against the page width, y
    against the page height, the units `domain.profile.NormalizedBBox` uses --
    so they can be compared directly with the 0.048 answer-column width Issue
    #122 measured.

    ``fit`` is ``None`` when this axis' printed ruling was too sparse or too
    crowded to determine a fit, and then only ``from_rotation`` is known.
    Reported rather than dropped: an answer form ruled for horizontal writing
    has plenty of rules across the page and almost none down it, so "not
    measurable on this axis" is a property of the form, not a failed run.
    """

    available: tuple[int, int]
    fit: AxisFit | None
    #: Why there is no fit, when there is none. Kept so the count of
    #: unmeasured axes can be read as evidence rather than as a shrug.
    reason: str | None
    #: Largest displacement each cause produces anywhere on the page.
    from_rotation: float
    from_scale: float | None
    from_translation: float | None
    #: All three together -- what a coordinate taken from page A is actually
    #: off by when applied to page B.
    total: float | None


@dataclass(frozen=True)
class PairDrift:
    """The measured difference between two scans of one printed form."""

    rotation_degrees: float
    x: AxisDrift
    y: AxisDrift

    @property
    def measured(self) -> bool:
        """Whether either axis yielded a fit."""
        return self.x.fit is not None or self.y.fit is not None


def measure_page(png_bytes: bytes) -> PageScan:
    """Deskew one rendered page and measure the printed rules on it."""
    image = _decode(png_bytes)
    height, width = int(image.shape[0]), int(image.shape[1])
    skew = _skew_degrees(image)
    ruling = measure_page_ruling(_encode(_rotate(image, -skew, border=255)))
    return PageScan(
        width=width,
        height=height,
        skew_degrees=skew,
        vertical=ruling.vertical,
        horizontal=ruling.horizontal,
    )


def measure_pair(a: PageScan, b: PageScan) -> PairDrift:
    """The drift from ``a`` to ``b``.

    Always returns a result. An axis that could not be measured says so and
    says why, rather than collapsing the whole pair into a silence: two pages
    that share no ruling are two different forms -- a continuation sheet
    against a first page -- and that is a finding about the corpus, not a
    failed run. `PairDrift.measured` is the question "did anything come of
    this pair".
    """
    rotation = b.skew_degrees - a.skew_degrees
    turn_x, turn_y = _rotation_displacement(rotation, a.width, a.height)
    return PairDrift(
        rotation_degrees=rotation,
        x=_axis_drift(a.vertical, b.vertical, rotation, turn_x, a.width, a.height, axis=0),
        y=_axis_drift(a.horizontal, b.horizontal, rotation, turn_y, a.width, a.height, axis=1),
    )


def _axis_drift(
    a_lines: Sequence[float],
    b_lines: Sequence[float],
    rotation: float,
    from_rotation: float,
    width: int,
    height: int,
    *,
    axis: int,
) -> AxisDrift:
    available = (len(a_lines), len(b_lines))
    fit, reason = _fit_axis(a_lines, b_lines)
    if fit is None:
        return AxisDrift(available, None, reason, from_rotation, None, None, None)
    return AxisDrift(
        available=available,
        fit=fit,
        reason=None,
        from_rotation=from_rotation,
        from_scale=abs(fit.scale - 1.0) / 2.0 if fit.scale_measured else None,
        from_translation=abs(_shift_at_centre(fit)),
        total=_total_displacement(rotation, fit, width, height, axis=axis),
    )


def _shift_at_centre(fit: AxisFit) -> float:
    """The fit's translation measured where it is least confounded with its
    scale -- the middle of the page. ``shift`` alone is the displacement at
    the page *edge*, where a 1% scale error already contributes nothing."""
    return fit.scale * 0.5 + fit.shift - 0.5


def _rotation_displacement(degrees: float, width: int, height: int) -> tuple[float, float]:
    """How far rotating the page about its centre by ``degrees`` moves the
    point it moves furthest, per axis, page-normalized.

    A rotation about the centre moves a point by ``theta * r`` perpendicular to
    its radius, so x is displaced most by the points furthest up or down the
    page, and y by those furthest left or right.
    """
    radians = math.radians(abs(degrees))
    return (radians * (height / 2.0) / width, radians * (width / 2.0) / height)


def _total_displacement(
    rotation: float, fit: AxisFit, width: int, height: int, *, axis: int
) -> float:
    """The largest displacement rotation, scale and translation together
    produce on this axis, anywhere on the page.

    Evaluated at the page corners rather than added up per cause: rotation and
    translation can cancel as easily as they can compound, and the sum of the
    three worst cases is a number the page never actually shows.

    The *other* axis enters only through the rotation, which multiplies it by
    ``sin(rotation)``. Its own fit is therefore taken as the identity, whether
    or not it was measurable: at the largest rotation and translation seen
    here that approximation is worth under 0.0002 of the page, a tenth of the
    smallest number this probe reports.
    """
    angle = math.radians(rotation)
    cos, sin = math.cos(angle), math.sin(angle)
    worst = 0.0
    for corner_x, corner_y in ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)):
        fitted_x = fit.scale * corner_x + fit.shift if axis == 0 else corner_x
        fitted_y = corner_y if axis == 0 else fit.scale * corner_y + fit.shift
        # Rotate about the page centre in pixels -- rotating normalized
        # coordinates would shear a non-square page.
        offset_x, offset_y = (fitted_x - 0.5) * width, (fitted_y - 0.5) * height
        if axis == 0:
            worst = max(worst, abs((offset_x * cos - offset_y * sin) / width + 0.5 - corner_x))
        else:
            worst = max(worst, abs((offset_x * sin + offset_y * cos) / height + 0.5 - corner_y))
    return worst


def _fit_axis(
    a_lines: Sequence[float], b_lines: Sequence[float]
) -> tuple[AxisFit | None, str | None]:
    """The scale-and-shift relating ``a_lines`` to ``b_lines``, or ``None`` and
    the reason no honest one exists.

    Found by translation first, then scale -- not by searching both at once.
    The two scans do not carry the same *set* of rules (a student's
    handwriting hides some and its own long strokes add others), so a search
    with two free parameters can always buy extra matches by tilting the
    slope, and on these pages it did: it returned scales of 4-5% on the pairs
    where it matched fewest rules. Translation alone has one parameter and no
    such freedom, and a real scan-to-scan scale is small enough that the
    correct translation still lines up most of the page. From those matches
    the slope is then measured rather than searched, and the rules re-paired
    against it until the pairing stops changing.
    """
    if len(a_lines) < MIN_MATCHED_RULES or len(b_lines) < MIN_MATCHED_RULES:
        return None, TOO_FEW_RULES
    sources = np.asarray(a_lines, dtype=float)
    targets = np.asarray(b_lines, dtype=float)
    shift = _best_shift(sources, targets)
    if shift is None:
        return None, NO_ALIGNMENT
    free = _refine(sources, targets, shift)
    fit = (
        free
        if free is not None and abs(free.scale - 1.0) <= _MAX_SCALE_DRIFT
        else _translation_only(sources, targets, shift, len(a_lines), len(b_lines))
    )
    if fit is None:
        return None, NO_ALIGNMENT
    if _has_rival(sources, targets, fit):
        return None, AMBIGUOUS
    return fit, None


def _has_rival(sources: np.ndarray, targets: np.ndarray, fit: AxisFit) -> bool:
    """Whether some *other* alignment explains the ruling about as well.

    A form's rules are close to a ladder, and a ladder can be read off by one
    rung: on one real page pair the winning alignment said the sheet had moved
    0.04 to the left, while sliding the same rules one rung the other way said
    it had stretched 3% to the right, and the two agreed on almost as many
    rules as each other. Neither is a measurement. This is what tells them
    apart from a page where only one alignment works, and it is why an
    ambiguous axis is dropped rather than averaged: the two readings do not
    differ in size, they differ in sign.
    """
    separation = _RIVAL_SEPARATION * _MATCH_TOLERANCE
    chosen = fit.scale * 0.5 + fit.shift - 0.5
    offsets = targets[None, :] - sources[:, None]
    candidates = offsets[np.abs(offsets) <= _SHIFT_SPAN]
    rivals = candidates[np.abs(candidates - chosen) > separation]
    if rivals.size == 0:
        return False
    nearest = np.abs(offsets[None, :, :] - rivals[:, None, None]).min(axis=2)
    return bool((nearest <= _MATCH_TOLERANCE).sum(axis=1).max() >= fit.matched - _RIVAL_MARGIN)


def _refine(sources: np.ndarray, targets: np.ndarray, shift: float) -> AxisFit | None:
    """Let scale and shift both move, re-pairing the rules after each step
    until the pairing stops changing."""
    scale = 1.0
    pairs = _pair_up(sources, targets, scale, shift)
    for _ in range(_REFINE_PASSES):
        if len(pairs) < MIN_MATCHED_RULES:
            return None
        scale, shift = _least_squares(pairs)
        repaired = _pair_up(sources, targets, scale, shift)
        if repaired == pairs:
            break
        pairs = repaired
    if not _is_well_determined(pairs, min(len(sources), len(targets))):
        return None
    return _to_fit(pairs, scale, shift, len(sources), len(targets), scale_measured=True)


def _translation_only(
    sources: np.ndarray, targets: np.ndarray, shift: float, available_a: int, available_b: int
) -> AxisFit | None:
    """The best fit with the scale pinned at 1.

    Used when the free fit asked for a physically impossible stretch. Pinning
    the scale keeps the axis in the results with the two numbers that are still
    honest -- how far the page moved, and how much of it that fails to explain
    -- instead of dropping the page or reporting the stretch.
    """
    pairs = _pair_up(sources, targets, 1.0, shift)
    if not _is_well_determined(pairs, min(available_a, available_b)):
        return None
    settled = float(np.mean([target - source for source, target in pairs]))
    pairs = _pair_up(sources, targets, 1.0, settled)
    if not _is_well_determined(pairs, min(available_a, available_b)):
        return None
    return _to_fit(pairs, 1.0, settled, available_a, available_b, scale_measured=False)


def _to_fit(
    pairs: Sequence[tuple[float, float]],
    scale: float,
    shift: float,
    available_a: int,
    available_b: int,
    *,
    scale_measured: bool,
) -> AxisFit:
    return AxisFit(
        matched=len(pairs),
        available_a=available_a,
        available_b=available_b,
        scale=scale,
        shift=shift,
        max_residual=max(abs(target - (scale * source + shift)) for source, target in pairs),
        scale_measured=scale_measured,
    )


def _best_shift(sources: np.ndarray, targets: np.ndarray) -> float | None:
    """The translation that brings the most rules together, ties broken by how
    closely it brings them.

    Only shifts that land some rule of A exactly on some rule of B are tried:
    between two of those the set of matches cannot change, so the rest of the
    range holds nothing to find.
    """
    offsets = targets[None, :] - sources[:, None]
    candidates = offsets[np.abs(offsets) <= _SHIFT_SPAN]
    if candidates.size == 0:
        return None
    nearest = np.abs(offsets[None, :, :] - candidates[:, None, None]).min(axis=2)
    hit = nearest <= _MATCH_TOLERANCE
    counts = hit.sum(axis=1)
    closeness = np.where(hit, nearest, 0.0).sum(axis=1)
    best = min(np.flatnonzero(counts == counts.max()), key=lambda index: closeness[index])
    return float(candidates[best]) if counts[best] >= MIN_MATCHED_RULES else None


def _is_well_determined(pairs: Sequence[tuple[float, float]], available: int) -> bool:
    """Whether the matched rules are enough of the page, and enough of the
    ruling, for their slope to mean anything."""
    if len(pairs) < max(MIN_MATCHED_RULES, round(_MIN_MATCH_FRACTION * available)):
        return False
    matched = [source for source, _ in pairs]
    return max(matched) - min(matched) >= _MIN_MATCH_SPAN


def _pair_up(
    sources: np.ndarray, targets: np.ndarray, scale: float, shift: float
) -> list[tuple[float, float]]:
    """The rules the winning transform brings together, one target per source,
    closest pair first so a rule cannot be claimed by a worse match."""
    predicted = scale * sources + shift
    ranked = sorted(
        (abs(target - predicted[i]), i, j)
        for i, _ in enumerate(sources)
        for j, target in enumerate(targets)
        if abs(target - predicted[i]) <= _MATCH_TOLERANCE
    )
    used_sources: set[int] = set()
    used_targets: set[int] = set()
    pairs: list[tuple[float, float]] = []
    for _, i, j in ranked:
        if i in used_sources or j in used_targets:
            continue
        used_sources.add(i)
        used_targets.add(j)
        pairs.append((float(sources[i]), float(targets[j])))
    return pairs


def _least_squares(pairs: Sequence[tuple[float, float]]) -> tuple[float, float]:
    sources = np.asarray([source for source, _ in pairs], dtype=float)
    targets = np.asarray([target for _, target in pairs], dtype=float)
    scale, shift = np.polyfit(sources, targets, 1)
    return float(scale), float(shift)


def _skew_degrees(image: np.ndarray) -> float:
    """How far the page is rotated from upright, in the same sense as
    `cv2.getRotationMatrix2D` -- so ``-skew`` is the rotation that squares it
    up again.

    Found by the angle that makes the ink pile up hardest into rows and
    columns: a printed form is mostly straight rules and lines of text, so its
    projection profiles are spikiest -- highest variance -- when it is square
    to the axes. Measured on a half-scale copy: the answer is an angle, and
    halving the pixels changes it by far less than `_SKEW_FINE_STEP`.
    """
    small = cv2.resize(image, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    ink = (small <= _INK_LEVEL).astype(np.float32)

    def sharpness(correction: float) -> float:
        rotated = _rotate(ink, correction, border=0.0)
        return float(rotated.sum(axis=0).var() + rotated.sum(axis=1).var())

    coarse = max(np.arange(-_SKEW_SPAN, _SKEW_SPAN + 1e-12, _SKEW_COARSE_STEP), key=sharpness)
    fine = np.arange(
        coarse - _SKEW_COARSE_STEP, coarse + _SKEW_COARSE_STEP + 1e-12, _SKEW_FINE_STEP
    )
    return -float(max(fine, key=sharpness))


def _rotate(image: np.ndarray, degrees: float, *, border: float) -> np.ndarray:
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), degrees, 1.0)
    return cv2.warpAffine(
        image, matrix, (width, height), flags=cv2.INTER_LINEAR, borderValue=border
    )


def _decode(png_bytes: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("could not decode page image")
    return image


def _encode(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("could not encode page image")
    return bytes(buffer.tobytes())
