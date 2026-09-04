"""Persistence tests for `ProfileStore` (Issue #11's app-data/tests/<id>/profile.json layout)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from auto_scoring.adapters.local import ProfileStore
from auto_scoring.domain.profile import (
    FormatSignature,
    NormalizedBBox,
    PageFormat,
    Profile,
    ProfileStatus,
    Region,
    RegionKind,
)

_SIGNATURE = FormatSignature(pages=(PageFormat(595.0, 842.0), PageFormat(842.0, 595.0)))


def _draft_profile(profile_id: str = "profile-1", format_id: str = "format-a") -> Profile:
    regions = (
        Region(
            region_id="q1",
            kind=RegionKind.QUESTION,
            page_index=0,
            bbox=NormalizedBBox(0.1, 0.1, 0.5, 0.2),
            label="Q1",
        ),
        Region(
            region_id="answer",
            kind=RegionKind.ANSWER_AREA,
            page_index=1,
            bbox=NormalizedBBox(0.2, 0.3, 0.9, 0.8),
            label="ANSWER_1",
        ),
    )
    return Profile.from_candidates(profile_id, format_id, _SIGNATURE, regions)


def test_save_then_load_reproduces_the_profile_exactly(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "app-data")
    draft = _draft_profile()

    store.save(draft)
    reloaded = store.load(draft.format_id)

    assert reloaded == draft
    assert reloaded.status is ProfileStatus.DRAFT
    assert all(not region.confirmed for region in reloaded.regions)


def test_confirmed_save_overwrites_the_draft_at_the_same_path(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "app-data")
    draft = _draft_profile()
    store.save(draft)
    draft_path = store.profile_path(draft.format_id)

    confirmed = draft.confirm([replace(region, confirmed=True) for region in draft.regions])
    confirmed_path = store.save(confirmed)

    assert confirmed_path == draft_path
    reloaded = store.load(draft.format_id)
    assert reloaded.status is ProfileStatus.CONFIRMED
    assert reloaded == confirmed


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "app-data")
    store.save(_draft_profile())

    target_dir = store.profile_path("format-a").parent
    leftovers = list(target_dir.glob("*.part"))
    assert leftovers == []
    assert (target_dir / "profile.json").is_file()


def test_load_reads_from_disk_not_a_cached_object(tmp_path: Path) -> None:
    """A second `ProfileStore` instance (standing in for a separate process) sees the same data."""
    root = tmp_path / "app-data"
    ProfileStore(root).save(_draft_profile())

    reloaded = ProfileStore(root).load("format-a")

    assert reloaded == _draft_profile()


def test_different_formats_are_stored_independently(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "app-data")
    a = _draft_profile(profile_id="profile-a", format_id="format-a")
    b = _draft_profile(profile_id="profile-b", format_id="format-b")

    store.save(a)
    store.save(b)

    assert store.load("format-a") == a
    assert store.load("format-b") == b


def test_profile_path_rejects_escaping_the_storage_root(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "app-data")
    with pytest.raises(ValueError, match="escapes storage root"):
        store.profile_path("../../outside")
