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


#: Ink coverage at or below which a cropped answer image counts as "nothing
#: was cut out but paper" -- see :func:`is_nearly_blank_crop`.
#:
#: **Measured, and deliberately set to catch only the unambiguous case**
#: (Issue #122). On three real answer sheets:
#:
#: * a region of blank paper measures ``0.000015`` or less
#: * a crop that landed on a question the student answered measures
#:   ``0.050``-``0.121``
#: * a crop the detector put in the margin measured ``0.0000`` exactly
#: * a crop that landed *half* on the answer measured ``0.034``-``0.062`` --
#:   overlapping the range real answers occupy
#:
#: So this sits two orders of magnitude above blank paper and more than an
#: order below the thinnest real answer, and the half-off case is **not**
#: caught on purpose. There is no coverage number that separates "the box is
#: half wrong" from "the student wrote little", and a threshold raised until
#: it caught them would start rejecting real answers while still missing
#: others. That case is for a person to see, not for this to rule on
#: (Issue #122's second half).
NEARLY_BLANK_INK_COVERAGE = 0.002

#: `AnswerImage.reason` for a crop this rejected. Matches the existing
#: ``no_answer_area_defined`` / ``answer_area_zero_area`` vocabulary.
NEARLY_BLANK_CROP_REASON = "crop_nearly_blank"

#: `AnswerImage.reason` for a crop the *grading AI itself* reported is not
#: this question's answer (Issue #136, `domain.models.AnswerImageFinding.
#: NOT_THE_ANSWER`). Same vocabulary, same contract, one difference in
#: timing: every other reason here is decided before the question is graded,
#: and this one can only be known from the grading response --
#: `jobs.grading_processor` writes it, intake never does.
#:
#: Why the crop's own record and not just the failed `Job`: a job's
#: ``last_error`` is the last attempt's diagnosis, while this is a durable
#: property of the crop. Recording it here means the next attempt skips the
#: provider entirely (`jobs.recognition_processor` /
#: `jobs.grading_processor` both stop on `AnswerImageStatus.NEEDS_REVIEW`),
#: and "how often does the detector hand grading the wrong region?" can be
#: counted later without re-running anything.
#:
#: This exact string also reaches the review screen inside the job's
#: ``last_error`` (`jobs.grading_processor._crop_not_the_answer`), where the
#: app matches on it to say what to fix -- `app/lib/core/
#: grading_failure_reason.dart` holds the other half.
NOT_THE_ANSWER_CROP_REASON = "crop_not_the_answer"

#: `AnswerImage.reason` when the confirmed answer areas for two questions sit
#: in the opposite order to their numbers on the page they share (Issue #213,
#: building on Issue #171's detection). Same contract as the other intake
#: reasons: the crop is kept so a person can see what would have been graded,
#: but `jobs.recognition_processor` / `jobs.grading_processor` never send it
#: to a provider -- an adjacent question's plausible answer is indistinguishable
#: to the AI, and confidence is no help (one real run scored 0/4 at 1.00).
READING_ORDER_CONFLICT_REASON = "reading_order_conflict"


def is_nearly_blank_crop(ink_coverage: float) -> bool:
    """Whether a cropped answer image holds so little ink that sending it to
    be graded would be grading a piece of blank paper.

    Two different things land here and this cannot tell them apart: the
    answer area is in the wrong place, or the student left the question
    blank. **Both belong in front of a person**, and the existing contract
    already says so -- `AnswerImageStatus.NEEDS_REVIEW` means "the crop
    itself could not be trusted", and `jobs.grading_processor` skips grading
    for it without calling the provider. Before Issue #122 a blank crop went
    to the AI instead, which answered "空白なので0点" with a confidence of
    0.95-1.00: a wrong score that looked exactly like a right one.
    """
    return ink_coverage <= NEARLY_BLANK_INK_COVERAGE
