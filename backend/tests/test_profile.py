"""Unit tests for the Profile domain model's confirmation invariants."""

from __future__ import annotations

from dataclasses import replace

import pytest

from auto_scoring.domain.profile import (
    FormatSignature,
    NormalizedBBox,
    PageFormat,
    Profile,
    ProfileStatus,
    Region,
    RegionKind,
)

_SIGNATURE = FormatSignature(pages=(PageFormat(width_pt=595.0, height_pt=842.0),))


def _region(region_id: str, confirmed: bool = False) -> Region:
    return Region(
        region_id=region_id,
        kind=RegionKind.QUESTION,
        page_index=0,
        bbox=NormalizedBBox(x0=0.1, y0=0.1, x1=0.5, y1=0.2),
        label="Q1",
        confirmed=confirmed,
    )


def test_from_candidates_is_always_draft_and_unconfirmed() -> None:
    # A caller passing confirmed=True by mistake must not smuggle a candidate
    # straight to CONFIRMED -- this is the acceptance criterion that
    # candidates are always saved unconfirmed.
    sneaky = _region("q1", confirmed=True)
    profile = Profile.from_candidates("p1", "format-a", _SIGNATURE, [sneaky])
    assert profile.status is ProfileStatus.DRAFT
    assert all(not region.confirmed for region in profile.regions)


def test_confirm_requires_every_region_confirmed() -> None:
    profile = Profile.from_candidates("p1", "format-a", _SIGNATURE, [_region("q1")])
    with pytest.raises(ValueError, match="not confirmed"):
        profile.confirm([_region("q1", confirmed=False)])


def test_confirm_rejects_empty_region_list() -> None:
    profile = Profile.from_candidates("p1", "format-a", _SIGNATURE, [_region("q1")])
    with pytest.raises(ValueError, match="no regions"):
        profile.confirm([])


def test_confirm_transitions_to_confirmed_with_reviewed_regions() -> None:
    profile = Profile.from_candidates("p1", "format-a", _SIGNATURE, [_region("q1")])
    confirmed = profile.confirm([_region("q1", confirmed=True)])
    assert confirmed.status is ProfileStatus.CONFIRMED
    assert all(region.confirmed for region in confirmed.regions)
    # confirm() returns a new object; the draft is untouched.
    assert profile.status is ProfileStatus.DRAFT


@pytest.mark.parametrize(
    ("x0", "y0", "x1", "y1"),
    [
        (-0.1, 0.1, 0.5, 0.5),
        (0.1, 0.1, 1.5, 0.5),
        (0.5, 0.1, 0.1, 0.5),  # x0 >= x1
        (0.1, 0.5, 0.5, 0.5),  # y0 >= y1
    ],
)
def test_normalized_bbox_rejects_out_of_range_or_degenerate(
    x0: float, y0: float, x1: float, y1: float
) -> None:
    with pytest.raises(ValueError):
        NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def test_format_signature_matches_within_tolerance_only() -> None:
    a = FormatSignature(pages=(PageFormat(595.0, 842.0),))
    close = FormatSignature(pages=(PageFormat(595.4, 841.6),))
    far = FormatSignature(pages=(PageFormat(600.0, 842.0),))
    wrong_page_count = FormatSignature(pages=(PageFormat(595.0, 842.0), PageFormat(595.0, 842.0)))

    assert a.matches(close, tolerance_pt=1.0)
    assert not a.matches(far, tolerance_pt=1.0)
    assert not a.matches(wrong_page_count, tolerance_pt=1.0)


@pytest.mark.parametrize("dimensions", [(0.0, 842.0), (595.0, -1.0)])
def test_page_format_requires_positive_dimensions(dimensions: tuple[float, float]) -> None:
    with pytest.raises(ValueError, match="positive"):
        PageFormat(*dimensions)


def test_format_signature_requires_a_page() -> None:
    with pytest.raises(ValueError, match="at least one page"):
        FormatSignature(pages=())


def test_profile_rejects_region_outside_its_page_range() -> None:
    invalid = replace(_region("q1"), page_index=-1)
    with pytest.raises(ValueError, match="outside the format signature"):
        Profile.from_candidates("p1", "format-a", _SIGNATURE, [invalid])


def test_region_text_round_trips_through_to_dict_and_from_dict() -> None:
    """Issue #16 added `Region.text` for candidate-generated wording (rubric,
    score, model answer) -- it must survive a save/reload just like every
    other field.
    """
    region = replace(_region("q1"), text="5点満点")
    assert Region.from_dict(region.to_dict()) == region


def test_region_from_dict_defaults_text_to_none_for_pre_issue_16_data() -> None:
    """A profile.json saved before Issue #16 added `text` has no such key --
    it must still load, with `text` defaulting to `None`, not raise a
    `KeyError`.
    """
    region = _region("q1")
    data = region.to_dict()
    del data["text"]
    assert Region.from_dict(data).text is None


def test_a_profile_rejects_two_regions_sharing_an_id() -> None:
    """A region id is how everything downstream addresses one region -- the
    review screen selects by it, the 回答欄 editor opens its numeric dialog by
    it, and `PUT /profile` sends edits back keyed on it (Issue #105).

    Two regions with one id means an edit lands on whichever is found first
    while the other silently keeps its old value. `PUT /profile` accepts
    whatever a client sends, so the invariant has to live here.
    """
    with pytest.raises(ValueError, match="distinct ids"):
        Profile.from_candidates(
            "p1", "t1", _SIGNATURE, [_region("q1"), replace(_region("q1"), label="Q2")]
        )


def test_a_profile_rejects_a_duplicate_id_at_confirm_time_too() -> None:
    """`confirm` replaces the whole region set with a reviewer-supplied one,
    so it is a second way in and needs the same guarantee.
    """
    draft = Profile.from_candidates("p1", "t1", _SIGNATURE, [_region("q1")])
    with pytest.raises(ValueError, match="distinct ids"):
        draft.confirm([_region("q1", confirmed=True), _region("q1", confirmed=True)])


class TestAbsentQuestionNumbers:
    """What detection said about questions the paper has no space for
    (Issue #164).

    Stored, unlike everything else about "this question has no region",
    because it cannot be derived: a question with no `ANSWER_AREA` is either
    one detection missed or one the paper does not have, and nothing in the
    region set tells the two apart.
    """

    def _profile(self, **kwargs: object) -> Profile:
        return Profile(
            profile_id="p-1",
            format_id="f-1",
            signature=FormatSignature(pages=(PageFormat(width_pt=595.0, height_pt=842.0),)),
            regions=(),
            status=ProfileStatus.DRAFT,
            **kwargs,  # type: ignore[arg-type]
        )

    def test_it_survives_a_save_and_reload(self) -> None:
        original = self._profile(absent_question_numbers=("問3", "問4"))

        assert Profile.from_dict(original.to_dict()).absent_question_numbers == ("問3", "問4")

    def test_a_profile_saved_before_this_field_existed_still_loads(self) -> None:
        data = self._profile().to_dict()
        del data["absent_question_numbers"]

        assert Profile.from_dict(data).absent_question_numbers == ()

    def test_a_profile_that_never_ran_detection_claims_nothing(self) -> None:
        """Defaulting to "every question is on the sheet" would tell a
        reviewer who drew every box by hand that the paper is missing
        nothing -- true by accident, and false the moment it is not."""
        assert self._profile().absent_question_numbers == ()

    def test_confirming_carries_it_through(self) -> None:
        """The grading side reads it after confirmation, so losing it at the
        confirm step would put the distinction back where it was."""
        region = Region(
            region_id="r-1",
            kind=RegionKind.ANSWER_AREA,
            page_index=0,
            bbox=NormalizedBBox(x0=0.1, y0=0.1, x1=0.5, y1=0.5),
            label="問1",
            confirmed=True,
        )
        draft = self._profile(absent_question_numbers=("問3",))

        assert draft.confirm([region]).absent_question_numbers == ("問3",)
