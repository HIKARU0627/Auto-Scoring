"""Profile domain model.

A profile is a set of regions (question / answer area / annotation area /
score / rubric / model answer) bound to one document *format*. It is built in
two steps: auto-detected candidates (always unconfirmed, see
`Profile.from_candidates`), then a human review that produces a confirmed
profile (`Profile.confirm`) -- the only state `profile_apply.reapply_profile`
will accept. See docs/poc-4-multi-layout-profiles.md (Issue #15).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any


class RegionKind(StrEnum):
    QUESTION = "question"
    ANSWER_AREA = "answer_area"
    ANNOTATION_AREA = "annotation_area"
    SCORE = "score"
    RUBRIC = "rubric"
    MODEL_ANSWER = "model_answer"


@dataclass(frozen=True)
class NormalizedBBox:
    """Axis-aligned box in normalized page coordinates.

    Origin top-left, axes `0..1`, independent of page size/DPI/zoom -- the
    same convention PoC 3 (Issue #12) adopted for annotation coordinates.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        for name, value in (("x0", self.x0), ("y0", self.y0), ("x1", self.x1), ("y1", self.y1)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within 0..1, got {value}")
        if self.x0 >= self.x1 or self.y0 >= self.y1:
            raise ValueError(f"bbox must have positive area: {self}")

    def max_corner_distance(self, other: NormalizedBBox) -> float:
        """Largest absolute per-corner difference; the metric `reapply_profile`'s tolerance uses."""
        return max(
            abs(self.x0 - other.x0),
            abs(self.y0 - other.y0),
            abs(self.x1 - other.x1),
            abs(self.y1 - other.y1),
        )

    def to_dict(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NormalizedBBox:
        return cls(
            x0=float(data["x0"]), y0=float(data["y0"]), x1=float(data["x1"]), y1=float(data["y1"])
        )


@dataclass(frozen=True)
class Region:
    region_id: str
    kind: RegionKind
    page_index: int
    bbox: NormalizedBBox
    label: str
    confirmed: bool = False
    #: Extracted text content for kinds that carry one (QUESTION prompt,
    #: MODEL_ANSWER, RUBRIC, SCORE). ``None`` for purely-positional kinds
    #: (ANSWER_AREA, ANNOTATION_AREA) that only mark where something goes.
    #: Added in Issue #16 so a candidate generated from real PDF text (rather
    #: than the PoC's tagged annotations) can carry its source text through
    #: human review and into the confirmed `Question`/`Rubric` it becomes --
    #: see `domain.test_registration`. Optional with a default for backward
    #: compatibility with profiles saved before this field existed.
    text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "kind": self.kind.value,
            "page_index": self.page_index,
            "bbox": self.bbox.to_dict(),
            "label": self.label,
            "confirmed": self.confirmed,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Region:
        confirmed = data["confirmed"]
        if not isinstance(confirmed, bool):
            raise ValueError("region confirmed must be a boolean")
        text = data.get("text")
        if text is not None and not isinstance(text, str):
            raise ValueError("region text must be a string or null")
        return cls(
            region_id=str(data["region_id"]),
            kind=RegionKind(data["kind"]),
            page_index=int(data["page_index"]),
            bbox=NormalizedBBox.from_dict(data["bbox"]),
            label=str(data["label"]),
            confirmed=confirmed,
            text=text,
        )


@dataclass(frozen=True)
class PageFormat:
    width_pt: float
    height_pt: float

    def __post_init__(self) -> None:
        if self.width_pt <= 0.0 or self.height_pt <= 0.0:
            raise ValueError("page dimensions must be positive")

    @property
    def is_landscape(self) -> bool:
        return self.width_pt > self.height_pt

    def to_dict(self) -> dict[str, float]:
        return {"width_pt": self.width_pt, "height_pt": self.height_pt}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PageFormat:
        return cls(width_pt=float(data["width_pt"]), height_pt=float(data["height_pt"]))


@dataclass(frozen=True)
class FormatSignature:
    """Coarse geometry check for a document layout: page count + per-page size.

    Reapplication also requires the explicit ``format_id`` to match. Dimensions
    alone cannot distinguish two layouts that use the same paper size.
    """

    pages: tuple[PageFormat, ...]

    def __post_init__(self) -> None:
        if not self.pages:
            raise ValueError("format signature must contain at least one page")

    def matches(self, other: FormatSignature, tolerance_pt: float = 1.0) -> bool:
        if len(self.pages) != len(other.pages):
            return False
        return all(
            abs(a.width_pt - b.width_pt) <= tolerance_pt
            and abs(a.height_pt - b.height_pt) <= tolerance_pt
            for a, b in zip(self.pages, other.pages, strict=True)
        )

    def to_dict(self) -> dict[str, Any]:
        return {"pages": [page.to_dict() for page in self.pages]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FormatSignature:
        return cls(pages=tuple(PageFormat.from_dict(page) for page in data["pages"]))


class ProfileStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


def _pages_out_of_range(regions: Sequence[Region], signature: FormatSignature) -> list[str]:
    return [
        region.region_id for region in regions if not 0 <= region.page_index < len(signature.pages)
    ]


@dataclass(frozen=True)
class Profile:
    """Regions bound to one document format, at a point in its review lifecycle."""

    profile_id: str
    format_id: str
    signature: FormatSignature
    regions: tuple[Region, ...]
    status: ProfileStatus

    def __post_init__(self) -> None:
        invalid_pages = _pages_out_of_range(self.regions, self.signature)
        if invalid_pages:
            raise ValueError(
                f"regions reference pages outside the format signature: {invalid_pages}"
            )
        if self.status is ProfileStatus.CONFIRMED:
            if not self.regions:
                raise ValueError("cannot confirm a profile with no regions")
            unreviewed = [region.region_id for region in self.regions if not region.confirmed]
            if unreviewed:
                raise ValueError(f"regions not confirmed: {unreviewed}")
        elif any(region.confirmed for region in self.regions):
            raise ValueError("draft profile cannot contain confirmed regions")

    @classmethod
    def from_candidates(
        cls,
        profile_id: str,
        format_id: str,
        signature: FormatSignature,
        regions: Sequence[Region],
    ) -> Profile:
        """Save auto-detected candidates. Always DRAFT; forces every region unconfirmed.

        This is the acceptance criterion "生成候補は必ず未確認状態で保存され、
        人間確認なしに登録完了にならない" (Issue #15) -- enforced here, not left
        to callers to remember.
        """
        unconfirmed = tuple(replace(region, confirmed=False) for region in regions)
        return cls(profile_id, format_id, signature, unconfirmed, ProfileStatus.DRAFT)

    def confirm(self, reviewed_regions: Sequence[Region]) -> Profile:
        """Human review step: replace the candidate regions with the reviewed set.

        Every region in `reviewed_regions` must already be marked
        `confirmed=True` -- the caller (a human, via the eventual review UI)
        attests to each one individually. A profile with any unconfirmed or
        missing region can never reach `ProfileStatus.CONFIRMED`, so
        `profile_apply.reapply_profile` can never see it.
        """
        if not reviewed_regions:
            raise ValueError("cannot confirm a profile with no regions")
        invalid_pages = _pages_out_of_range(reviewed_regions, self.signature)
        if invalid_pages:
            raise ValueError(
                f"regions reference pages outside the format signature: {invalid_pages}"
            )
        unreviewed = [region.region_id for region in reviewed_regions if not region.confirmed]
        if unreviewed:
            raise ValueError(f"regions not confirmed: {unreviewed}")
        return replace(self, regions=tuple(reviewed_regions), status=ProfileStatus.CONFIRMED)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-ready dict. See `adapters.local.profile_store.ProfileStore`."""
        return {
            "profile_id": self.profile_id,
            "format_id": self.format_id,
            "status": self.status.value,
            "signature": self.signature.to_dict(),
            "regions": [region.to_dict() for region in self.regions],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Profile:
        """Reconstruct a previously-saved profile verbatim, including its DRAFT/CONFIRMED status.

        The constructor re-validates page ranges and lifecycle invariants, so
        a hand-edited or corrupted file is rejected rather than reapplied.
        """
        signature = FormatSignature.from_dict(data["signature"])
        regions = tuple(Region.from_dict(region) for region in data["regions"])
        return cls(
            profile_id=str(data["profile_id"]),
            format_id=str(data["format_id"]),
            signature=signature,
            regions=regions,
            status=ProfileStatus(data["status"]),
        )
