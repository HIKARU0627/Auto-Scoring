"""Reapplies a confirmed profile to another document of the same format."""

from __future__ import annotations

from dataclasses import dataclass

from auto_scoring.domain.profile import FormatSignature, Profile, ProfileStatus, Region


class ProfileNotConfirmedError(Exception):
    """The profile hasn't been through human confirmation yet (still DRAFT)."""


class FormatMismatchError(Exception):
    """The target document's format signature doesn't match the profile's."""


@dataclass(frozen=True)
class AppliedProfile:
    """A confirmed profile's regions, bound to a specific target document."""

    source_profile_id: str
    target_format_id: str
    regions: tuple[Region, ...]


def reapply_profile(
    profile: Profile,
    target_format_id: str,
    target_signature: FormatSignature,
    tolerance_pt: float = 1.0,
) -> AppliedProfile:
    """Bind `profile`'s regions to another document, once its format is verified to match.

    Raises `ProfileNotConfirmedError` for a DRAFT profile and
    `FormatMismatchError` when the explicit format ID differs or the target's
    page count/sizes fall outside `tolerance_pt` -- Issue #15's requirement
    that a mismatched format never silently gets the wrong regions.
    """
    if profile.status is not ProfileStatus.CONFIRMED:
        raise ProfileNotConfirmedError(
            f"profile {profile.profile_id!r} is {profile.status.value}; "
            "only a confirmed profile can be reapplied"
        )
    if profile.format_id != target_format_id or not profile.signature.matches(
        target_signature, tolerance_pt=tolerance_pt
    ):
        raise FormatMismatchError(
            f"profile {profile.profile_id!r} format does not match target {target_format_id!r}"
        )
    return AppliedProfile(profile.profile_id, target_format_id, profile.regions)
