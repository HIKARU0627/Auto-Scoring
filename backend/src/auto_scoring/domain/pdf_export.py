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


#: The symbol put at the head of a shape-kind annotation's note line, so a
#: reader of the margin band can tell which note belongs to the ``×`` on the
#: answer and which to the ``○`` (Issue #141). `AnnotationKind.COMMENT` has
#: none on purpose: it is prose, not a mark, and §12.4's own example shows a
#: bare line of text.
_KIND_SYMBOLS: Mapping[AnnotationKind, str] = {
    AnnotationKind.CIRCLE: "○",
    AnnotationKind.CROSS: "×",
    AnnotationKind.TRIANGLE: "△",
    AnnotationKind.UNDERLINE: "＿",
    AnnotationKind.BOX: "□",
}

#: The final note line when `_note_marks` cannot give every note a legible
#: slice of the band. See `_note_marks` for why this exists rather than a
#: silent truncation.
_OVERFLOW_NOTE = "ほか{count}件は余白に収まらず未表示"

#: A note slice shorter than this (page-normalized) cannot hold a legible
#: line. `adapters.pdf.pdfium_pypdf_engine` draws text at `_MIN_FONT_SIZE_PT`
#: (6pt) on a `_LINE_HEIGHT_FACTOR` (1.2) baseline, i.e. 7.2pt, and the
#: shortest page this project handles is A4 portrait's 595pt-wide landscape
#: sibling -- 7.2/595 rounds up to this. Deliberately the same kind of
#: constant as `annotation_layout._MIN_DERIVED_BAND_HEIGHT`: a slice nothing
#: can be read in is not an output, it is a blank page with extra steps.
_MIN_NOTE_HEIGHT = 0.012


def _note_text(annotation: Annotation) -> str | None:
    """One margin-band line for ``annotation``, or ``None`` when it has
    nothing to say (a shape with no comment is fully expressed by the shape
    drawn on the answer itself).
    """
    comment = (annotation.comment or "").strip()
    if not comment:
        return None
    symbol = _KIND_SYMBOLS.get(annotation.kind)
    return f"{symbol} {comment}" if symbol else comment


def _stacked_note_rects(area: NormalizedRect, count: int) -> tuple[NormalizedRect, ...]:
    """``count`` equal, non-overlapping slices of ``area`` stacked top to
    bottom -- or as many as fit at `_MIN_NOTE_HEIGHT`, when ``count`` of them
    would not.

    Each note gets its own rect rather than all of them sharing one, because
    `PdfEngine.render_annotations` draws every mark from its own rect: one
    joined string would be re-wrapped and shrunk as a single block, so a
    single long comment could push every other note below the band's bottom
    edge and out of sight.
    """
    capacity = max(1, int(area.height / _MIN_NOTE_HEIGHT))
    slots = min(count, capacity)
    height = area.height / slots
    return tuple(
        NormalizedRect(x=area.x, y=area.y + index * height, width=area.width, height=height)
        for index in range(slots)
    )


def _note_marks(comment_area: NormalizedRect | None, notes: Sequence[str]) -> list[AnnotationMark]:
    """The margin-band marks for ``notes``, stacked inside ``comment_area``.

    **The overflow policy** (Issue #141): when the band cannot hold every
    note, the last slice says how many are missing (`_OVERFLOW_NOTE`) instead
    of the notes simply stopping. Issue #121 is the precedent -- a complete,
    correct grade was thrown away over a long comment and the run reported
    success -- and the same shape of mistake is available here: a question
    with a shallow ``comment_area`` and five annotations would show two of
    them and look finished. Counting what did not fit costs one line and
    makes the loss visible to the person holding the paper.

    An unregistered ``comment_area`` (``None``) leaves nowhere to write at
    all, and the notes are dropped -- `unplaceable_question_ids` refuses an
    export before it can reach that state for any question that has a
    ``score_area``, and since Issue #120 a question has both or neither.
    """
    if not notes or comment_area is None:
        return []
    rects = _stacked_note_rects(comment_area, len(notes))
    if len(rects) < len(notes):
        shown = len(rects) - 1
        notes = [*notes[:shown], _OVERFLOW_NOTE.format(count=len(notes) - shown)]
    return [
        AnnotationMark(kind=AnnotationKind.COMMENT, rect=rect, text=note)
        for rect, note in zip(rects, notes, strict=True)
    ]


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

    **Where an annotation's comment text goes** (Issue #141). Every
    annotation contributes at most two marks, and they are separate things:

    * its *shape* (``×``/``○``/``△``/underline/box), drawn on the answer at
      the rect `domain.annotation_layout.resolve_annotation_rect` resolved --
      and only when it resolved one;
    * its *comment*, always drawn as one line in the question's
      ``comment_area`` margin band (`_note_marks`), never on the answer.

    Splitting them is what Issue #141 found missing. `PdfEngine.
    render_annotations` renders a mark's ``text`` only for the SCORE and
    COMMENT kinds, so a ``×`` carrying an explanation had that explanation
    silently thrown away by the engine: the live run produced twelve
    annotations and not one character of their comments reached any page.
    Handing the comment to the band instead of to the shape also stops prose
    from being drawn across the student's own writing, which is what an
    anchored COMMENT-kind annotation used to do.

    A `COMMENT`-kind annotation therefore never draws a shape at all -- it
    has none -- and contributes only its band line. Each note gets its own
    slice of the band rather than every note sharing one rect: marks are
    drawn independently from their own top-left corner, so two notes on one
    rect would land on top of one another, both illegible, while the export
    still reported success (P2 review, round 5).
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
    notes: list[str] = []
    for annotation in attempt_annotations:
        # Its text and its rect would both be this mark's (§2.1: the number
        # comes from the confirmed grade, the position from `score_area`),
        # so drawing it too would just stack the same string on itself.
        if annotation.kind is AnnotationKind.SCORE:
            continue
        rect = resolve_annotation_rect(
            annotation, question=question, recognitions=attempt_recognitions
        )
        if rect is not None and annotation.kind is not AnnotationKind.COMMENT:
            marks.append(AnnotationMark(kind=annotation.kind, rect=rect))
        note = _note_text(annotation)
        if note is not None:
            notes.append(note)
    marks.extend(_note_marks(question.comment_area, notes))
    return marks


__all__ = [
    "ReexportDecision",
    "build_export_marks",
    "decide_reexport",
    "review_version_snapshot",
    "unconfirmed_question_ids",
    "unplaceable_question_ids",
]
