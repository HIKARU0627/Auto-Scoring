"""Tests for AI usage aggregation and cost rules (Issue #187)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from auto_scoring.domain.ai_usage import (
    UsageAvailability,
    apply_token_unit_cost,
    summarize_ai_grade_tokens,
)
from auto_scoring.domain.models import GradeResult, GradingSource, Score


def _ai_grade(
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> GradeResult:
    return GradeResult(
        id="grade-1",
        submission_id="sub-1",
        question_id="q-1",
        source=GradingSource.AI,
        score=Score(awarded=1, maximum=5),
        confidence=0.9,
        created_at=datetime.now(UTC),
        provider="openrouter",
        model="test/model",
        prompt_version="v1",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def test_unit_cost_unset_never_produces_estimated_cost() -> None:
    summary = apply_token_unit_cost(
        summarize_ai_grade_tokens([_ai_grade(input_tokens=1000, output_tokens=200)]),
        None,
    )
    assert summary.estimated_cost is None
    assert summary.token_unit_cost is None
    assert summary.totals is not None
    assert summary.totals.total_tokens == 1200


def test_usage_unknown_when_no_token_fields() -> None:
    summary = summarize_ai_grade_tokens([_ai_grade()])
    assert summary.availability is UsageAvailability.UNKNOWN
    assert summary.totals is None


def test_zero_yen_is_not_shown_via_estimated_cost_when_unit_cost_set() -> None:
    summary = apply_token_unit_cost(
        summarize_ai_grade_tokens([_ai_grade(input_tokens=0, output_tokens=0)]),
        1.5,
    )
    assert summary.estimated_cost == pytest.approx(0.0)


def test_partial_when_some_questions_lack_usage() -> None:
    summary = summarize_ai_grade_tokens(
        [
            _ai_grade(input_tokens=100, output_tokens=50),
            _ai_grade(),
        ]
    )
    assert summary.availability is UsageAvailability.PARTIAL
    assert summary.totals is not None
    assert summary.totals.total_tokens == 150
