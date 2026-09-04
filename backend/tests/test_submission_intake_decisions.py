"""Unit tests for domain.submission_intake: reintake policy and page coverage."""

from __future__ import annotations

from auto_scoring.domain.models import SubmissionState
from auto_scoring.domain.submission_intake import (
    PageCoverage,
    ReintakeDecision,
    decide_reintake,
    describe_coverage_issue,
)
from tests.support import make_submission


def test_decide_reintake_accepts_new_when_nothing_exists() -> None:
    assert decide_reintake(None) is ReintakeDecision.ACCEPT_NEW


def test_decide_reintake_rejects_duplicate_of_a_live_submission() -> None:
    for state in (
        SubmissionState.UNPROCESSED,
        SubmissionState.AI_PROCESSING,
        SubmissionState.AI_PROCESSED,
        SubmissionState.NEEDS_REVIEW,
        SubmissionState.REVIEWED,
        SubmissionState.EXPORTED,
    ):
        existing = make_submission(state=state)
        assert decide_reintake(existing) is ReintakeDecision.REJECT_DUPLICATE


def test_decide_reintake_retries_an_errored_submission() -> None:
    existing = make_submission(state=SubmissionState.ERROR)
    assert decide_reintake(existing) is ReintakeDecision.RETRY_EXISTING


def test_page_coverage_complete_when_pages_match() -> None:
    coverage = PageCoverage(expected_pages=(1, 2, 3), actual_page_count=3)
    assert coverage.is_complete
    assert coverage.missing_pages == ()
    assert not coverage.has_extra_pages
    assert describe_coverage_issue(coverage) is None


def test_page_coverage_detects_missing_pages() -> None:
    coverage = PageCoverage(expected_pages=(1, 2, 3), actual_page_count=2)
    assert not coverage.is_complete
    assert coverage.missing_pages == (3,)
    assert describe_coverage_issue(coverage) == "missing_pages:3"


def test_page_coverage_detects_extra_pages() -> None:
    coverage = PageCoverage(expected_pages=(1, 2), actual_page_count=4)
    assert not coverage.is_complete
    assert coverage.has_extra_pages
    assert describe_coverage_issue(coverage) == "extra_pages:4>2"


def test_page_coverage_with_no_expected_pages_is_complete() -> None:
    coverage = PageCoverage(expected_pages=(), actual_page_count=3)
    assert coverage.is_complete
