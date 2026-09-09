"""Pure rules for producing the annotated-PDF export (Issue #23, parent #3).

Framework-free (`AGENTS.md` "Architecture"): everything here is plain
functions over domain dataclasses already read by the caller
(`jobs.export_processor.ExportJobProcessor`) -- no repository, no PDF
library, no filesystem access. See `docs/pdf-export.md` for the full design
record this implements.

Two concerns live here:

* Gating: `unconfirmed_question_ids` (Issue #23 acceptance: "未確認設問がある
  場合は出力を拒否し、対象を表示する") and the review-version snapshot
  (`review_version_snapshot`) that lets a later export request tell whether
  anything changed since the last successful one (`decide_reexport`).
* Layout: `build_export_marks` turns one question's confirmed grade +
  annotations into the resolved, page-normalized `AnnotationMark` instructions
  `domain.pdf_engine.PdfEngine.render_annotations` draws.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum

from auto_scoring.domain.annotation_layout import (
    annotations_for_attempt,
    recognitions_up_to_attempt,
    resolve_annotation_rect,
)
from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    Export,
    GradeResult,
    NormalizedRect,
    Question,
    QuestionReviewVersion,
    RecognitionResult,
    Review,
)
from auto_scoring.domain.pdf_engine import AnnotationMark
from auto_scoring.domain.review_workflow import effective_latest_review, is_confirmed


def unconfirmed_question_ids(
    question_ids: Iterable[str], reviews_by_question: Mapping[str, Sequence[Review]]
) -> list[str]:
    """Every id in ``question_ids`` whose effective review is not confirmed
    (approved/modified and not since undone) -- the export-time twin of
    `domain.review_workflow.all_questions_confirmed`, but naming the specific
    questions so the caller can display them (Issue #23 acceptance).
    """
    return [
        question_id
        for question_id in question_ids
        if not is_confirmed(effective_latest_review(reviews_by_question.get(question_id, ())))
    ]


def unplaceable_question_ids(questions: Iterable[Question]) -> list[str]:
    """Every question with nowhere to draw its score -- no `score_area`, and
    none derivable from an answer box either (Issue #120).

    The twin of `unconfirmed_question_ids`, for the other way an export can
    come out blank. That one is about a human not having decided the grade
    yet; this one is about the page not having a place to put it. Both name
    the specific questions so the caller can show them, and both run
    *before* the job is queued: the live run's export succeeded, produced a
    file byte-for-byte identical to the answer sheet, and said nothing --
    which is the outcome this refuses.

    Only `score_area` is checked, not `comment_area`. The score is drawn for
    every question (`build_export_marks`), so a missing `score_area` always
    means something confirmed is missing from the page. A missing
    ``comment_area`` only matters when an annotation actually needed to fall
    back to it, and since Issue #120 both are derived from the same answer
    box -- a question that has one has the other.
    """
    return [question.id for question in questions if question.score_area is None]


def review_version_snapshot(
    question_ids: Iterable[str], reviews_by_question: Mapping[str, Sequence[Review]]
) -> tuple[QuestionReviewVersion, ...]:
    """The review-history length of every question in ``question_ids``, in a
    stable (sorted by id) order -- what `Export.review_versions` records, and
    what `decide_reexport` compares across two export attempts.

    Every id here is assumed already confirmed (`unconfirmed_question_ids`
    empty), so each history is non-empty and `len(...)` is a valid
    (``>= 1``) `QuestionReviewVersion.version`.
    """
    return tuple(
        QuestionReviewVersion(
            question_id=question_id, version=len(reviews_by_question.get(question_id, ()))
        )
        for question_id in sorted(question_ids)
    )


class ReexportDecision(StrEnum):
    """Issue #23 acceptance: "同一review versionの再出力方針が決定表どおり
    動作する" -- the decision table `decide_reexport` implements. Named and
    shaped after `domain.submission_intake.decide_reintake`'s own
    `ACCEPT_NEW`/`RETRY_EXISTING`/`REJECT_DUPLICATE` triad, the closest
    existing precedent for "should this write produce a new artifact, reuse
    an old one, or refuse".
    """

    #: No prior successful export for this submission exists yet.
    ACCEPT_NEW = "accept_new"
    #: A prior successful export exists and every question's review-history
    #: length is unchanged since -- nothing to re-render; hand back that
    #: export instead of generating a byte-for-byte equivalent duplicate file.
    REUSE_EXISTING = "reuse_existing"
    #: A prior successful export exists but at least one question's review
    #: history has moved on (a later edit/approve, or an Undo) -- render a
    #: new file (`LocalFileStore.allocate_export_path`'s own collision
    #: numbering names it); the previous file is left untouched
    #: (business-rules-and-evaluation-data.md §2 (15): never overwrite a
    #: prior output).
    ACCEPT_NEW_SUPERSEDING = "accept_new_superseding"


def decide_reexport(
    previous: Export | None, current_snapshot: Sequence[QuestionReviewVersion]
) -> ReexportDecision:
    """See `ReexportDecision`. Comparison is by value (question id + version
    pairs), not by `Export.id` or timestamp -- two exports are "the same
    review state" exactly when every question's review-history length
    matches, regardless of what produced either snapshot.
    """
    if previous is None:
        return ReexportDecision.ACCEPT_NEW
    if tuple(current_snapshot) == previous.review_versions:
        return ReexportDecision.REUSE_EXISTING
    return ReexportDecision.ACCEPT_NEW_SUPERSEDING


def _score_text(grade: GradeResult) -> str:
    return f"{grade.score.awarded}/{grade.score.maximum}"


def build_export_marks(
    *,
    question: Question,
    grade: GradeResult,
    annotations: Sequence[Annotation],
    recognitions: Sequence[RecognitionResult],
) -> list[AnnotationMark]:
    """The resolved `AnnotationMark` list to draw for one question's
    confirmed attempt: its effective ``grade`` (per `domain.review_workflow.
    resolve_effective_grade`) together with that question's *full*
    ``annotations``/``recognitions`` history -- this function itself scopes
    both down to the attempt ``grade`` belongs to (`annotations_for_attempt`/
    `recognitions_up_to_attempt`), the same "only this attempt's marks"
    filtering the review screen applies client-side
    (``docs/pdf-review-overlay.md`` §2.12), so a re-graded question's export
    never mixes marks from two different attempts.

    The score is drawn for every question that has a ``score_area``, from the
    confirmed ``grade`` itself (``awarded/maximum``) -- **not** from a
    `SCORE`-kind `Annotation`, which is skipped. The rule that the number
    comes from the confirmed `GradeResult` and never from an AI candidate's
    free-text label is unchanged (``docs/pdf-export.md`` "SCOREの描画文字列");
    what changed in Issue #120 is that it no longer waits for a proposal that
    may never arrive. Nothing in this repository creates a `SCORE` annotation,
    and in the live run no provider proposed one, so every exported PDF came
    out with no score written on it at all.

    A question with no ``score_area`` draws no score rather than one at a
    guessed position; `unplaceable_question_ids` refuses the export before it
    can reach that state.

    An annotation `domain.annotation_layout.resolve_annotation_rect` cannot
    place anywhere (no rect, no matching OCR box, not a fixed-position kind)
    falls back to ``question.comment_area`` (simplified-design-spec.md
    §12.4); one still unresolved after that (no `comment_area` registered
    either) is skipped -- there is nowhere left to draw it. Since Issue #120
    both areas are derived from the confirmed answer box when nobody placed
    them (`domain.annotation_layout.derive_mark_areas`), so a question that
    reaches an export has both or neither.

    A `COMMENT`-kind annotation that falls back this way is never drawn as
    its own mark: `PdfEngine.render_annotations` draws every mark
    independently from its rect's own top-left corner, so two or more
    COMMENT annotations all landing on the same ``comment_area`` (nothing
    else distinguishes where each individually belongs) would be drawn on
    top of one another, both illegible, while the export itself still
    reports success (P2 review, round 5). Every such comment is instead
    collected and drawn as a single merged text block -- one mark, its text
    the individual comments joined with a blank line -- so multiple
    unplaceable comments still show as several stacked paragraphs rather
    than overlapping text.
    """
    attempt_annotations = annotations_for_attempt(annotations, grade.created_at)
    attempt_recognitions = recognitions_up_to_attempt(recognitions, grade.created_at)
    marks: list[AnnotationMark] = []
    if question.score_area is not None:
        marks.append(
            AnnotationMark(
                kind=AnnotationKind.SCORE, rect=question.score_area, text=_score_text(grade)
            )
        )
    fallback_comment_texts: list[str] = []
    fallback_comment_rect: NormalizedRect | None = None
    for annotation in attempt_annotations:
        # Its text and its rect would both be this mark's (§2.1: the number
        # comes from the confirmed grade, the position from `score_area`),
        # so drawing it too would just stack the same string on itself.
        if annotation.kind is AnnotationKind.SCORE:
            continue
        rect = resolve_annotation_rect(
            annotation, question=question, recognitions=attempt_recognitions
        )
        used_fallback_rect = rect is None
        if used_fallback_rect:
            rect = question.comment_area
        if rect is None:
            continue
        text = annotation.comment
        if used_fallback_rect and annotation.kind is AnnotationKind.COMMENT:
            fallback_comment_texts.append(text or "")
            fallback_comment_rect = rect
            continue
        marks.append(AnnotationMark(kind=annotation.kind, rect=rect, text=text))
    if fallback_comment_texts:
        assert fallback_comment_rect is not None
        marks.append(
            AnnotationMark(
                kind=AnnotationKind.COMMENT,
                rect=fallback_comment_rect,
                text="\n\n".join(fallback_comment_texts),
            )
        )
    return marks


__all__ = [
    "ReexportDecision",
    "build_export_marks",
    "decide_reexport",
    "review_version_snapshot",
    "unconfirmed_question_ids",
    "unplaceable_question_ids",
]
