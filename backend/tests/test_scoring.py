"""Unit tests for the domain scoring rules."""

import pytest

from auto_scoring.domain.scoring import clamp_score


def test_clamp_score_keeps_value_in_range() -> None:
    result = clamp_score(raw=7, maximum=10)
    assert result.awarded == 7
    assert result.ratio == pytest.approx(0.7)


def test_clamp_score_clamps_low_and_high() -> None:
    assert clamp_score(raw=-3, maximum=10).awarded == 0
    assert clamp_score(raw=42, maximum=10).awarded == 10


def test_clamp_score_zero_maximum_has_zero_ratio() -> None:
    assert clamp_score(raw=0, maximum=0).ratio == 0.0


def test_clamp_score_rejects_negative_maximum() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        clamp_score(raw=1, maximum=-1)
