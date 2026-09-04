"""Unit tests for reapply_profile's status/format gates (no PDFs needed)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from auto_scoring.domain.profile import (
    FormatSignature,
    NormalizedBBox,
    PageFormat,
    Profile,
    Region,
    RegionKind,
)
from auto_scoring.domain.profile_apply import (
    FormatMismatchError,
    ProfileNotConfirmedError,
    reapply_profile,
)

_SIGNATURE_A = FormatSignature(pages=(PageFormat(595.0, 842.0),))
_SIGNATURE_B = FormatSignature(pages=(PageFormat(842.0, 595.0),))  # landscape: different format


def _draft_profile() -> Profile:
    region = Region(
        region_id="q1",
        kind=RegionKind.QUESTION,
        page_index=0,
        bbox=NormalizedBBox(0.1, 0.1, 0.5, 0.2),
        label="Q1",
    )
    return Profile.from_candidates("p1", "format-a", _SIGNATURE_A, [region])


def test_reapply_rejects_unconfirmed_profile() -> None:
    draft = _draft_profile()
    with pytest.raises(ProfileNotConfirmedError):
        reapply_profile(draft, "target-1", _SIGNATURE_A)


def test_reapply_rejects_format_mismatch() -> None:
    draft = _draft_profile()
    confirmed = draft.confirm([replace(region, confirmed=True) for region in draft.regions])
    with pytest.raises(FormatMismatchError):
        reapply_profile(confirmed, "target-1", _SIGNATURE_B)


def test_reapply_succeeds_for_matching_confirmed_profile() -> None:
    draft = _draft_profile()
    confirmed = draft.confirm([replace(region, confirmed=True) for region in draft.regions])
    applied = reapply_profile(confirmed, "target-1", _SIGNATURE_A)
    assert applied.source_profile_id == "p1"
    assert applied.target_format_id == "target-1"
    assert applied.regions == confirmed.regions
