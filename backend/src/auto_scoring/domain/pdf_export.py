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


def fallback_score_areas(questions: Iterable[Question]) -> dict[str, NormalizedRect]:
    """Where each question with no `score_area` gets its score written
    instead, keyed by question id (Issue #150).

    **Why there is a fallback at all.** Issue #120 refused the whole export
    when any question had nowhere to draw, because the alternative it faced
    was a PDF byte-for-byte identical to the answer sheet. Live re-run #4
    showed what that refusal costs in practice: four of seven subjects could
    not be exported at all, every one of them after a human had confirmed
    every single question, because the answer-box detection had missed some
    boxes (Issue #131). Refusing threw away *all* of that confirmed work to
    protect the part of it that had no home.

    Both of the outcomes this replaces are worse than a margin note:

    * dropping the unplaceable question's score and exporting the rest is
      Issue #121's failure exactly -- a confirmed grade discarded while the
      run reports success, with nothing on the paper to show it happened;
    * refusing is the Issue #137 dead end by another route -- the reviewer
      finished the work and cannot get the artefact out, and (before Issue
      #150's other half) was told to go and confirm what was already
      confirmed.

    **Why the margin and not next to the answer.** Because the position is
    exactly what is not known: these questions have no answer box, so any
    spot on the page would be a guess dressed as knowledge. That is the
    mistake Issue #141 removed for annotations whose anchor matched nothing,
    and the reasoning carries over unchanged. The margin claims nothing
    about where on the page the question was; it says only "this question
    scored this", which is true and is the thing that would otherwise be
    lost. Each line therefore names its question (`build_export_marks`) --
    a bare ``3/5`` in a margin belongs to nothing.

    Questions keep their page (`Question.page`), so each page's strip holds
    only that page's questions, stacked in the order they were registered.
    A question the strip cannot hold is left out of the result entirely and
    `unplaceable_question_ids` then names it: better to refuse than to write
    a score the reader cannot read (`_MIN_FALLBACK_SCORE_HEIGHT`).
    """
    by_page: dict[int, list[Question]] = {}
    for question in questions:
        if question.score_area is None:
            by_page.setdefault(question.page, []).append(question)
    areas: dict[str, NormalizedRect] = {}
    for page_questions in by_page.values():
        slots = _fallback_score_slots(len(page_questions))
        for question, slot in zip(page_questions, slots, strict=False):
            areas[question.id] = slot
    return areas


def unplaceable_question_ids(questions: Iterable[Question]) -> list[str]:
    """Every question whose score cannot be written anywhere at all -- no
    `score_area` of its own (Issue #120) *and* no slice of its page's
    fallback strip left to put it in (Issue #150).

    The twin of `unconfirmed_question_ids`, for the other way an export can
    come out blank. That one is about a human not having decided the grade
    yet; this one is about the page not having a place to put it. Both name
    the specific questions so the caller can show them, and both run
    *before* the job is queued: the live run's export succeeded, produced a
    file byte-for-byte identical to the answer sheet, and said nothing --
    which is the outcome this refuses.

    **Issue #150 narrowed this to what it is really for.** It used to mean
    "no ``score_area``", which in live re-run #4 was true of some question on
    four of the seven subjects and blocked all four. `fallback_score_areas`
    now gives those questions a place, so what is left here is only the case
    where even that runs out: a page with more unplaceable questions than its
    margin strip can hold legibly. That is a real refusal and not a
    theoretical one -- the alternative is drawing scores the reader cannot
    read -- but it is no longer the common one, and the caller must say which
    refusal it is (`api.export_router.ExportConflictCode`).

    Only `score_area` is checked, not `comment_area`. The score is drawn for
    every question (`build_export_marks`), so a missing `score_area` always
    means something confirmed is missing from the page. A missing
    ``comment_area`` only matters when an annotation actually needed to fall
    back to it, and since Issue #120 both are derived from the same answer
    box -- a question that has one has the other.
    """
    placeable = fallback_score_areas(questions)
    return [
        question.id
        for question in questions
        if question.score_area is None and question.id not in placeable
    ]


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

#: Appended to a note whose annotation could not be placed on the answer
#: (Issue #141). Saying so is the whole point: the reader has a comment about
#: their answer and no mark pointing at anything, and a note that stayed
#: silent about it would look like a mark that failed to print.
_UNPLACED_SUFFIX = "（位置特定できず）"

#: A note slice shorter than this (page-normalized) cannot hold a legible
#: line. `adapters.pdf.pdfium_pypdf_engine` draws text at `_MIN_FONT_SIZE_PT`
#: (6pt) on a `_LINE_HEIGHT_FACTOR` (1.2) baseline, i.e. 7.2pt, and the
#: shortest page this project handles is A4 portrait's 595pt-wide landscape
#: sibling -- 7.2/595 rounds up to this. Deliberately the same kind of
#: constant as `annotation_layout._MIN_DERIVED_BAND_HEIGHT`: a slice nothing
#: can be read in is not an output, it is a blank page with extra steps.
_MIN_NOTE_HEIGHT = 0.012

#: The page-normalized strip a score falls back into when its own question
#: has nowhere to put it (Issue #150) -- the sheet's left margin, running
#: from just below the top edge to just above the bottom one.
#:
#: **Measured on the real material, not chosen for looking tidy.** Every
#: answer page in the target set (13 pages across the 11 subjects that ship
#: one) was rendered and its dark-pixel density taken in 1%-of-width slices,
#: with the scan's own page frame excluded. ``x`` in [0.00, 0.03] came back
#: empty -- at most 0.02% dark, i.e. nothing -- on 12 of the 13; the
#: exception is one subject whose [0.01, 0.02] slice holds a scan-edge
#: artefact, and every question of that subject has its own `score_area`, so
#: it never reaches this fallback. On all four subjects Issue #150 blocks the
#: strip holds at most 0.15%, a few stray specks. Wider is not safe: from
#: [0.03, 0.05] outward, four subjects start showing printed rules and text.
#:
#: See ``docs/pdf-export.md`` §2.2.2 for the numbers, and for why writing here
#: beats both alternatives (dropping the score, refusing the export).
_FALLBACK_SCORE_STRIP = NormalizedRect(x=0.005, y=0.05, width=0.03, height=0.90)

#: The shortest slice of `_FALLBACK_SCORE_STRIP` a fallback score can be read
#: in. Four `_MIN_NOTE_HEIGHT` lines rather than one: the strip is only 3% of
#: the page wide (about 18pt on A4), so "問1 4/5" wraps down it over several
#: lines, and a slice too short for them all would be *truncated with an
#: ellipsis* (`adapters.pdf.pdfium_pypdf_engine._draw_text`) -- which can eat
#: the score itself. A margin note may be cut short; a score may not.
_MIN_FALLBACK_SCORE_HEIGHT = _MIN_NOTE_HEIGHT * 4


def _fallback_score_slots(count: int) -> tuple[NormalizedRect, ...]:
    """``count`` slices of `_FALLBACK_SCORE_STRIP`, or as many as fit at
    `_MIN_FALLBACK_SCORE_HEIGHT` when ``count`` of them would not."""
    return _stacked_rects(_FALLBACK_SCORE_STRIP, count, _MIN_FALLBACK_SCORE_HEIGHT)


def _note_text(annotation: Annotation, *, placed: bool) -> str | None:
    """One margin-band line for ``annotation``, or ``None`` when it has
    nothing to say.

    ``placed`` is whether a shape for it was drawn on the answer, and only a
    shape kind cares: `AnnotationKind.COMMENT` has no shape, so the band is
    simply where a comment lives (§12.4's own example is a bare line of
    text) and marking it "unplaced" would be noise on every one of them.

    A shape kind that *was* placed needs no marker either -- the reader can
    see the mark. One that was not says so (`_UNPLACED_SUFFIX`), even with no
    comment to carry: a bare ``× （位置特定できず）`` is little, but it is the
    difference between "something was marked here and we could not locate it"
    and silence.
    """
    comment = (annotation.comment or "").strip()
    symbol = _KIND_SYMBOLS.get(annotation.kind)
    if symbol is None:
        return comment or None
    if placed:
        return f"{symbol} {comment}" if comment else None
    return f"{symbol} {comment}{_UNPLACED_SUFFIX}" if comment else f"{symbol} {_UNPLACED_SUFFIX}"


def _stacked_rects(
    area: NormalizedRect, count: int, minimum_height: float
) -> tuple[NormalizedRect, ...]:
    """``count`` equal, non-overlapping slices of ``area`` stacked top to
    bottom -- or as many as fit at ``minimum_height``, when ``count`` of them
    would not.

    Each item gets its own rect rather than all of them sharing one, because
    `PdfEngine.render_annotations` draws every mark from its own rect: one
    joined string would be re-wrapped and shrunk as a single block, so a
    single long comment could push every other note below the band's bottom
    edge and out of sight.

    ``minimum_height`` is the caller's, not this function's, because what
    counts as legible depends on what is being written: an annotation note
    may be cut short at one line (`_MIN_NOTE_HEIGHT`), a score may not
    (`_MIN_FALLBACK_SCORE_HEIGHT`).
    """
    capacity = max(1, int(area.height / minimum_height))
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
    rects = _stacked_rects(comment_area, len(notes), _MIN_NOTE_HEIGHT)
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
    fallback_score_area: NormalizedRect | None = None,
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

    A question with no ``score_area`` draws no score at a guessed position.
    It draws one in ``fallback_score_area`` instead when the caller supplies
    one (`fallback_score_areas` -- the page's margin strip, Issue #150), and
    that line names its question, because a score in the margin has nothing
    beside it to say which question it belongs to. With no fallback either,
    no score is drawn and `unplaceable_question_ids` has already refused the
    export before it could reach that state.

    **Where an annotation's comment text goes** (Issue #141). Every
    annotation contributes at most two marks, and they are separate things:

    * its *shape* (``×``/``○``/``△``/underline/box), drawn on the answer at
      the rect `domain.annotation_layout.resolve_annotation_rect` resolved --
      and **only** when it resolved one. An annotation whose anchor matched
      nothing gets no shape at all: the position is not known, so nothing on
      the answer may claim to know it (Issue #141);
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
    has none -- and contributes only its band line. A line whose annotation
    could not be placed says so (`_UNPLACED_SUFFIX`), so an unplaced mark is
    visibly unplaced rather than absent. Each note gets its own
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
    elif fallback_score_area is not None:
        marks.append(
            AnnotationMark(
                kind=AnnotationKind.SCORE,
                rect=fallback_score_area,
                text=f"{question.number} {_score_text(grade)}",
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
        note = _note_text(annotation, placed=rect is not None)
        if note is not None:
            notes.append(note)
    marks.extend(_note_marks(question.comment_area, notes))
    return marks


__all__ = [
    "ReexportDecision",
    "build_export_marks",
    "decide_reexport",
    "fallback_score_areas",
    "review_version_snapshot",
    "unconfirmed_question_ids",
    "unplaceable_question_ids",
]
