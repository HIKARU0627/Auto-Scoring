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

from auto_scoring.domain.pdf_geometry import PageGeometry, UserSpacePoint, user_space_to_normalized
from auto_scoring.domain.profile import (
    FormatSignature,
    NormalizedBBox,
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


def requires_manual_fallback(markers: Sequence[Marker], profile: Profile) -> bool:
    """Whether detection is incomplete enough that registration must stop for manual input."""
    detected_kinds = {region.kind for region in profile.regions}
    required_kinds = {RegionKind.QUESTION, RegionKind.ANSWER_AREA}
    return bool(unrecognized_tags(markers)) or not required_kinds <= detected_kinds


def rect_to_bbox(rect_pt: RectPt, geometry: PageGeometry) -> NormalizedBBox:
    """Convert a PDF user-space rectangle to a normalized bbox via the adopted transform.

    Applies `user_space_to_normalized` (PoC 3 / Issue #12) to all four corners
    and takes their bounding box, rather than assuming axes stay aligned --
    correct under CropBox insets and any `/Rotate` (a 90/270 rotation swaps
    which axis maps to width vs. height).
    """
    x0, y0, x1, y1 = rect_pt
    corners = (
        user_space_to_normalized(UserSpacePoint(x, y), geometry)
        for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1))
    )
    xs: list[float] = []
    ys: list[float] = []
    for point in corners:
        xs.append(point.x)
        ys.append(point.y)
    return NormalizedBBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))


def generate_candidates(
    profile_id: str,
    format_id: str,
    signature: FormatSignature,
    page_geometries: Sequence[PageGeometry],
    markers: Sequence[Marker],
) -> Profile:
    """Build a DRAFT profile from the markers whose tag is recognized.

    `page_geometries` must align 1:1 with `signature.pages` (and with the
    document `markers` was read from) -- it carries the CropBox offset and
    `/Rotate` the simple width/height in `signature` cannot represent.
    Markers with an unrecognized tag are dropped -- call `unrecognized_tags`
    first if the caller needs to surface them (e.g. to prompt a human for a
    manual region instead of registering an incomplete profile).
    """
    if len(page_geometries) != len(signature.pages):
        raise ValueError("page_geometries must have one entry per page in signature")
    regions = []
    for index, marker in enumerate(markers):
        kind = classify_tag(marker.tag)
        if kind is None:
            continue
        if not 0 <= marker.page_index < len(signature.pages):
            raise ValueError(f"marker {marker.tag!r} references invalid page {marker.page_index}")
        geometry = page_geometries[marker.page_index]
        regions.append(
            Region(
                region_id=f"{marker.tag}-{index}",
                kind=kind,
                page_index=marker.page_index,
                bbox=rect_to_bbox(marker.rect_pt, geometry),
                label=marker.tag,
                confirmed=False,
            )
        )
    return Profile.from_candidates(profile_id, format_id, signature, regions)
