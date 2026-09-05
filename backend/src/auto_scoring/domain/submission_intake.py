"""Decisions the answer-intake pipeline makes without touching I/O.

Two things Issue #17's acceptance criteria requires be *deterministic and
documented* rather than an implicit choice buried in the API layer -- see
``docs/answer-intake-and-preprocessing.md`` for the full rationale:

* the reintake policy for "the same PDF submitted again" (§2 of that doc)
* how missing/extra pages relative to a test's registered questions are
  detected, given the MVP has no confirmed question-dependency DAG yet (§3)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from auto_scoring.domain.models import Submission, SubmissionState


class ReintakeDecision(StrEnum):
    """What to do when a PDF is submitted for a test it may already have."""

    #: No prior submission with this content hash exists for the test.
    ACCEPT_NEW = "accept_new"
    #: A prior submission with this content hash exists and is not errored, or
    #: is errored but not safely retryable in place; refuse silently
    #: overwriting it.
    REJECT_DUPLICATE = "reject_duplicate"
    #: A prior submission with this content hash exists, ended in ``ERROR``,
    #: and nothing downstream of intake has touched it yet; retry it in place
    #: instead of piling up dead rows for the same bytes.
    RETRY_EXISTING = "retry_existing"


def decide_reintake(
    existing: Submission | None, *, has_downstream_processing: bool = False
) -> ReintakeDecision:
    """Decide what happens when ``existing`` already has this PDF's content hash.

    ``existing`` is looked up by ``(test_id, source_pdf_sha256)`` -- the same
    bytes submitted again for the same test. ``has_downstream_processing``
    (from ``SubmissionRepository.has_downstream_processing``) says whether any
    recognition/grade/review/job row already references it: intake's in-place
    retry only replaces ``answer_images`` and re-derives the submission's own
    state, so retrying a submission something downstream (a later issue --
    OCR/AI grading) has already produced results for would leave that
    append-only history and any queued job orphaned against freshly
    regenerated images, rather than actually undoing the failed attempt. Such
    a submission is reported the same as any other non-retryable duplicate;
    resolving it (e.g. ``purge_submission``, once a replacement flow exists
    for a submission that has downstream results) is a human decision this
    function does not make on its own.
    """
    if existing is None:
        return ReintakeDecision.ACCEPT_NEW
    if existing.state is SubmissionState.ERROR and not has_downstream_processing:
        return ReintakeDecision.RETRY_EXISTING
    return ReintakeDecision.REJECT_DUPLICATE


@dataclass(frozen=True, kw_only=True)
class PageCoverage:
    """Compares a submission's actual page count against the pages its test's
    registered questions expect (``{q.page for q in questions}``).

    The MVP has no confirmed question-dependency DAG (business-rules-and-
    evaluation-data.md §4 scopes that to the test-registration issue), so this
    takes the conservative reading of §4.5 "確定DAGが存在しないテスト...は
    逐次処理にフォールバックし、人間へ「依存関係が未確定」の警告を出す":
    *any* page shortfall or surplus blocks the whole submission rather than
    trying to guess which questions are safe.
    """

    expected_pages: tuple[int, ...]
    actual_page_count: int

    @property
    def missing_pages(self) -> tuple[int, ...]:
        return tuple(sorted({p for p in self.expected_pages if p > self.actual_page_count}))

    @property
    def has_extra_pages(self) -> bool:
        return bool(self.expected_pages) and self.actual_page_count > max(self.expected_pages)

    @property
    def is_complete(self) -> bool:
        return not self.missing_pages and not self.has_extra_pages


def describe_coverage_issue(coverage: PageCoverage) -> str | None:
    """A short, stable machine-readable reason string, or ``None`` if complete.

    Stored on ``Submission.review_reason`` so a human reviewer (and the
    Flutter intake screen) sees *why* a submission needs attention without
    re-deriving it.
    """
    if coverage.is_complete:
        return None
    parts: list[str] = []
    if coverage.missing_pages:
        parts.append("missing_pages:" + ",".join(str(p) for p in coverage.missing_pages))
    if coverage.has_extra_pages:
        parts.append(f"extra_pages:{coverage.actual_page_count}>{max(coverage.expected_pages)}")
    return ";".join(parts)
