"""Turns tagged spans from an upstream extraction layer into candidate regions.

Issue #15 scopes the extraction itself out of this PoC: `Marker` is the
boundary. This PoC's own adapter
(`auto_scoring.adapters.pdf.annotation_markers`) sources markers from PDF
annotations placed at known positions -- a stand-in for a real text/vision
layer such as OCR (Issue #13), which would populate the same `Marker` shape
from detected text instead.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from auto_scoring.domain.profile import (
    FormatSignature,
    NormalizedBBox,
    PageFormat,
    Profile,
    Region,
    RegionKind,
)

RectPt = tuple[float, float, float, float]
"""(x0, y0, x1, y1) in PDF user-space points, origin bottom-left, corners in any order."""


@dataclass(frozen=True)
class Marker:
    """A tagged span already located on a page."""

    page_index: int
    tag: str
    rect_pt: RectPt


_TAG_PATTERNS: tuple[tuple[re.Pattern[str], RegionKind], ...] = (
    (re.compile(r"^Q\d+$"), RegionKind.QUESTION),
    (re.compile(r"^ANSWER(_\d+)?$"), RegionKind.ANSWER_AREA),
    (re.compile(r"^ANNOT(_\d+)?$"), RegionKind.ANNOTATION_AREA),
    (re.compile(r"^SCORE$"), RegionKind.SCORE),
    (re.compile(r"^RUBRIC$"), RegionKind.RUBRIC),
    (re.compile(r"^MODEL_ANSWER$"), RegionKind.MODEL_ANSWER),
)


def classify_tag(tag: str) -> RegionKind | None:
    """Map a marker tag to the region kind it represents, or `None` if unrecognized."""
    for pattern, kind in _TAG_PATTERNS:
        if pattern.match(tag):
            return kind
    return None


def unrecognized_tags(markers: Sequence[Marker]) -> list[str]:
    """Tags no known kind claims -- the per-format signal to fall back to manual regions."""
    return sorted({marker.tag for marker in markers if classify_tag(marker.tag) is None})


def _rect_to_bbox(rect_pt: RectPt, page: PageFormat) -> NormalizedBBox:
    x0, y0, x1, y1 = rect_pt
    left, right = sorted((x0, x1))
    bottom, top = sorted((y0, y1))
    return NormalizedBBox(
        x0=left / page.width_pt,
        y0=(page.height_pt - top) / page.height_pt,
        x1=right / page.width_pt,
        y1=(page.height_pt - bottom) / page.height_pt,
    )


def generate_candidates(
    profile_id: str,
    format_id: str,
    signature: FormatSignature,
    markers: Sequence[Marker],
) -> Profile:
    """Build a DRAFT profile from the markers whose tag is recognized.

    Markers with an unrecognized tag are dropped -- call `unrecognized_tags`
    first if the caller needs to surface them (e.g. to prompt a human for a
    manual region instead of registering an incomplete profile).
    """
    regions = []
    for index, marker in enumerate(markers):
        kind = classify_tag(marker.tag)
        if kind is None:
            continue
        page = signature.pages[marker.page_index]
        regions.append(
            Region(
                region_id=f"{marker.tag}-{index}",
                kind=kind,
                page_index=marker.page_index,
                bbox=_rect_to_bbox(marker.rect_pt, page),
                label=marker.tag,
                confirmed=False,
            )
        )
    return Profile.from_candidates(profile_id, format_id, signature, regions)
