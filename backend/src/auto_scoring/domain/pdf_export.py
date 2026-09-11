"""Pure rules for producing the annotated-PDF export (Issue #23, parent #3).

Framework-free (`AGENTS.md` "Architecture"): everything here is plain
functions over domain dataclasses already read by the caller
(`jobs.export_processor.ExportJobProcessor`) -- no repository, no PDF
library, no filesystem access. See `docs/pdf-export.md` for the full design
record this implements.

Two concerns live here:

* Gating: `export_refusal` (`unconfirmed_question_ids` -- Issue #23
  acceptance: "未確認設問がある場合は出力を拒否し、対象を表示する" -- plus
  `unplaceable_question_ids`) and the review-version snapshot
  (`review_version_snapshot`) that lets a later export request tell whether
  anything changed since the last successful one (`decide_reexport`).
* Layout: `build_export_marks` turns one question's confirmed grade +
  annotations into the resolved, page-normalized `AnnotationMark` instructions
  `domain.pdf_engine.PdfEngine.render_annotations` draws, plus the note lines
  that have nowhere on the answer sheet to go; `build_note_pages` lays those
  out on appended pages of their own (Issue #161).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import ceil

from auto_scoring.domain.annotation_layout import (
    annotations_for_attempt,
    recognitions_up_to_attempt,
    resolve_annotation_rects,
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


@dataclass(frozen=True, kw_only=True)
class NoteEntry:
    """One annotation note waiting for a place on an appended note page.

    ``page`` is the **1-based** page of the answer sheet the question sits
    on and ``question_number`` its `Question.number`: together they are how
    a reader holding a physically separate sheet finds what the note is
    about (`_note_entry_line`).
    """

    page: int
    question_number: str
    text: str


@dataclass(frozen=True, kw_only=True)
class QuestionExport:
    """What one question contributes to the exported PDF (Issue #161).

    Two different destinations, which is why this is a pair and not one
    list: ``marks`` are drawn onto the answer sheet itself, on the page the
    question is on; ``unplaced_notes`` have no rect on that sheet at all and
    go to an appended note page (`build_note_pages`).

    ``unplaced_notes`` is empty whenever the question has a ``comment_area``
    -- a human placed an ``ANNOTATION_AREA`` region, and their band is where
    the notes go, exactly as before. It carries every note when there is
    none, which since Issue #161 is every question registered by detection.
    """

    marks: tuple[AnnotationMark, ...]
    unplaced_notes: tuple[str, ...]


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
    refusal it is (`ExportRefusalReason`).

    Only `score_area` is checked, not `comment_area`. The score is drawn for
    every question (`build_export_marks`), so a missing `score_area` always
    means something confirmed is missing from the page. A missing
    ``comment_area`` cannot cost anything at all since Issue #161: the notes
    that used to depend on one now go to an appended note page
    (`build_note_pages`), which every export can always produce.
    """
    placeable = fallback_score_areas(questions)
    return [
        question.id
        for question in questions
        if question.score_area is None and question.id not in placeable
    ]


class ExportRefusalReason(StrEnum):
    """Why the sidecar refuses to export one submission -- the two gates
    `export_refusal` evaluates, and the wire values the client reads.

    The values travel verbatim: as ``detail.code`` on the single export's
    409 (`api.export_router`) and as ``refusal_code`` on a bulk item
    (Issue #142). They live here rather than in the API layer because the
    *distinction* is a domain fact, not a transport one -- what the reviewer
    must do next differs completely between the two, and both the single
    and the bulk path must name it the same way.

    Issue #150 is why naming it at all is not optional. Until then the two
    refusals shared one ``{message, question_ids}`` shape with nothing to
    tell them apart, and the Flutter client -- written when only
    `UNCONFIRMED_QUESTIONS` existed -- rendered both as "未確認の設問がある
    ため出力できません". In the live run a reviewer who had already confirmed
    every question was told to go and confirm them: an instruction that was
    not merely unhelpful but unfollowable, since the work it asked for was
    already done.
    """

    #: Issue #23: at least one question has no confirmed review yet.
    #: Confirming them makes the export possible.
    UNCONFIRMED_QUESTIONS = "unconfirmed_questions"
    #: Issue #120/#150: at least one question's score cannot be written
    #: anywhere -- neither at its own `Question.score_area` nor in its
    #: page's fallback band. **Confirming changes nothing here**; the page
    #: itself has no room, so this is not something the reviewer can
    #: resolve from the review screen.
    NO_ROOM_FOR_SCORE = "no_room_for_score"


@dataclass(frozen=True, kw_only=True)
class ExportRefusal:
    """One refusal, with the questions it is about (`ExportRefusalReason`)."""

    reason: ExportRefusalReason
    question_ids: tuple[str, ...]


def export_refusal(
    questions: Sequence[Question], reviews_by_question: Mapping[str, Sequence[Review]]
) -> ExportRefusal | None:
    """Whether this submission may be exported right now, and if not, why.

    Both gates in one function so the single export (which turns a refusal
    into a 409) and the bulk export (which turns it into one skipped row and
    keeps going, Issue #142) can never drift apart on *which* submissions
    are exportable. `unconfirmed_question_ids` is checked first because it
    is the one the reviewer can act on.
    """
    missing = unconfirmed_question_ids([question.id for question in questions], reviews_by_question)
    if missing:
        return ExportRefusal(
            reason=ExportRefusalReason.UNCONFIRMED_QUESTIONS, question_ids=tuple(sorted(missing))
        )
    # Issue #120: the other way an export comes out blank. The live run's
    # export returned 202, succeeded, and wrote a file byte-for-byte
    # identical to the answer sheet, because no question had anywhere to
    # draw. Refused before a job is queued rather than handed back as an
    # empty PDF.
    unplaceable = unplaceable_question_ids(questions)
    if unplaceable:
        return ExportRefusal(
            reason=ExportRefusalReason.NO_ROOM_FOR_SCORE, question_ids=tuple(sorted(unplaceable))
        )
    return None


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


def _fallback_score_text(question: Question, grade: GradeResult) -> str:
    """The margin strip's line for one question: **the score first, then the
    question it belongs to.**

    The number has to be there at all because a bare ``4/5`` in a margin
    belongs to nothing -- this mark is nowhere near the answer, which is the
    whole reason it exists (`fallback_score_areas`).

    It comes *second* because of what happens when the line does not fit.
    `adapters.pdf.pdfium_pypdf_engine._draw_text` wraps to the rect's width
    and, when even the 6pt floor leaves more lines than the rect can hold,
    keeps the first ones and ends the last with an ellipsis. Whatever is last
    in this string is therefore what gets eaten. The strip is 3% of the page
    wide -- about 18pt, three Japanese characters -- and `domain.
    test_registration` lets a `number` be up to
    ``_MAX_QUESTION_NUMBER_BYTES`` (40) bytes, which measures at nine wrapped
    lines for a 40-character ASCII label. With the number first, that label
    would push the score off the end and the export would still report
    success: a confirmed grade lost, with nothing on the paper to say so
    (Issue #121's failure again).

    Score first makes the truncation land on the label instead, where it is
    both survivable and *visible* -- the reader sees ``4/5 第一問設問三…``
    and still has the number that matters. No cap is applied to the number
    here on purpose: the engine's own ellipsis already says "there was more",
    and a second, silent truncation of our own would say nothing.
    """
    return f"{_score_text(grade)} {question.number}"


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


def _note_marks(comment_area: NormalizedRect, notes: Sequence[str]) -> list[AnnotationMark]:
    """The margin-band marks for ``notes``, stacked inside ``comment_area``.

    **The overflow policy** (Issue #141): when the band cannot hold every
    note, the last slice says how many are missing (`_OVERFLOW_NOTE`) instead
    of the notes simply stopping. Issue #121 is the precedent -- a complete,
    correct grade was thrown away over a long comment and the run reported
    success -- and the same shape of mistake is available here: a question
    with a shallow ``comment_area`` and five annotations would show two of
    them and look finished. Counting what did not fit costs one line and
    makes the loss visible to the person holding the paper.

    Only reached for a question that *has* a band, i.e. one a human placed
    an ``ANNOTATION_AREA`` region for. Since Issue #161 every other question
    has none, and `build_export_marks` routes its notes to an appended note
    page (`build_note_pages`) rather than passing ``None`` here to be
    silently dropped -- which is what this function used to accept.
    """
    if not notes:
        return []
    rects = _stacked_rects(comment_area, len(notes), _MIN_NOTE_HEIGHT)
    if len(rects) < len(notes):
        shown = len(rects) - 1
        notes = [*notes[:shown], _OVERFLOW_NOTE.format(count=len(notes) - shown)]
    return [
        AnnotationMark(kind=AnnotationKind.COMMENT, rect=rect, text=note)
        for rect, note in zip(rects, notes, strict=True)
    ]


#: The font size (pt) an appended note page is laid out for, and the line box
#: (pt) one wrapped line of it gets.
#:
#: **These two numbers are what stops a note from being silently shrunk or
#: cut**, and they are picked against `adapters.pdf.pdfium_pypdf_engine.
#: _draw_text`'s actual behaviour rather than being a wish. That function
#: starts at ``min(14, max(6, rect_height_pt))``, steps down one point at a
#: time while the wrapped lines do not fit, and -- if even its 6pt floor
#: leaves too many -- keeps the ones that fit and ends the last with an
#: ellipsis.
#:
#: Give a note ``n`` line boxes of 12pt and the sizes it tries are
#: ``min(14, 12n)``, one less, one less again: for every ``n`` that sequence
#: contains exactly ``10.0``, because both ``12`` and ``14`` are a whole
#: number of points above it. `_wrapped_line_count` is measured at 10pt and
#: over-estimates (see there), so 10pt always fits in ``12n`` line boxes, so
#: the descent stops at 10pt or above and never reaches the ellipsis branch.
#: A note is drawn at **at least 10pt, always** -- not "6pt if it has to",
#: which is the size at which the reader is handed a blur instead of a
#: sentence.
_NOTE_PAGE_FONT_SIZE_PT = 10.0
_NOTE_PAGE_LINE_HEIGHT_PT = 12.0

#: Page-normalized margin kept on all four sides of a note page. A note that
#: runs into the printer's own unprintable margin is as lost as one that was
#: cut.
_NOTE_PAGE_MARGIN = 0.06


def _chars_per_line(width_pt: float) -> int:
    """How many characters of a note line are *guaranteed* to fit across
    ``width_pt`` at `_NOTE_PAGE_FONT_SIZE_PT`.

    One character per point of font size, i.e. one em each. That is the
    width of a full-width Japanese glyph and an over-estimate for every
    other character the export can draw -- Latin, digits and punctuation are
    all narrower in the proportional gothic faces `adapters.pdf.
    pdfium_pypdf_engine._JAPANESE_FONT_CANDIDATES` names -- so the engine's
    real wrap always produces this many lines or fewer.

    Over-estimating is the point. `_draw_text` is what actually wraps, and
    this module never sees its font metrics: the domain is framework-free
    (`AGENTS.md` "Architecture") and cannot measure a glyph. An estimate
    that could come out *under* the truth would hand the engine a rect one
    line too short and get the note ellipsis-truncated -- Issue #121's
    failure in miniature -- while one that comes out over wastes a few
    points of paper and cannot lose a character.
    """
    return max(1, int(width_pt // _NOTE_PAGE_FONT_SIZE_PT))


def _wrapped_line_count(text: str, width_pt: float) -> int:
    return max(1, ceil(len(text) / _chars_per_line(width_pt)))


def _note_entry_line(entry: NoteEntry) -> str:
    """One note page line: **where it belongs first, then what it says.**

    The opposite order to `_fallback_score_text`, for the opposite reason.
    That line puts its score first because the margin strip is narrow enough
    to truncate and whatever is last is what gets eaten. A note page
    truncates nothing (`_NOTE_PAGE_FONT_SIZE_PT`), so nothing needs
    protecting by position, and the reference can go where it is actually
    useful: at the head of every line, so a reader holding a sheet that is
    physically separate from the answer can find the question a note is
    about without having to read the note first.
    """
    return f"第{entry.page}頁 {entry.question_number} {entry.text}"


def note_page_heading(*, test_name: str, submission_id: str) -> str:
    """The line every appended note page carries, naming what it belongs to.

    A note page is a separate sheet of paper. Staples come out, printers
    collate wrongly, and a sheet of sentences with no answer beside it is
    unattributable -- so the sheet has to say, on its own, which test and
    which submission it came from.

    **It deliberately adds no personal data.** Not the student's name, not
    the uploaded filename (which is free text a user may well have typed a
    name into): only the test's own name and the submission id, which is the
    same opaque handle the app and `Export` rows use. Whatever the answer
    sheet already prints about the student stays the answer sheet's --
    reprinting it here would put it somewhere it was not before, on a sheet
    that can be separated from the answer, for no gain (`AGENTS.md`
    "Security").
    """
    return f"注釈一覧　{test_name}　答案ID {submission_id}"


def build_note_pages(
    entries: Sequence[NoteEntry],
    *,
    heading: str,
    page_width_pt: float,
    page_height_pt: float,
) -> list[tuple[AnnotationMark, ...]]:
    """``entries`` laid out on as many appended note pages as they need --
    one `AnnotationMark` tuple per page, in order (Issue #161).

    **Why the notes leave the answer sheet at all.** Issue #141 moved every
    annotation's comment off the student's writing and into its question's
    ``comment_area`` band, on the understanding that the band was empty
    paper. It was not: the live re-verification measured that derived band
    on inked content for fourteen of sixteen answer-box questions, the worst
    at 19.1% against 0.0015% for blank paper. Issue #159 fixed the score
    half of the same defect by moving scores to a margin strip that had been
    *measured* empty. A comment cannot follow it there -- the strip is 3% of
    the page, about 18pt, and the real material's longest note needs 42
    wrapped lines in it.

    So those pages were measured again, for anywhere else prose could go,
    and there is nowhere. Across the eight subjects' answer sheets the
    widest truly-blank vertical strip is 4.0-7.5% of the page width (0.0% on
    two of them), which turns one page's notes into 18-63% of its height;
    the tallest blank full-width horizontal strip is 2.7-5.6% of the height,
    and on six of the eight it is the top margin above the header rather
    than the bottom, while the notes themselves need 3.6-11.5%. Take the
    width and the notes overlap the answer; avoid the overlap and they get
    cut. An appended page is the only placement that is neither.

    **What that costs.** One extra sheet per answer that has notes, and a
    reference one step more indirect: the shape on the answer and the
    sentence about it are no longer side by side. `_note_entry_line` is what
    makes the second cost payable -- every line names its page and question
    -- and ``heading`` is what keeps the sheet identifiable once a stapler
    or a printer has separated it from the answer it belongs to.

    **An answer with no notes gets no page.** Appending a near-empty sheet
    to every export would cost a sheet of paper per submission for nothing,
    and forty answers is forty sheets.

    **Nothing here is ever truncated.** A page holds as many whole notes as
    fit and the rest start a new one (`_paginate`). The only thing that may
    be cut is ``heading``, and only on a page too small to hold it *and* a
    note: it repeats what the app already knows, and a note does not.
    """
    if not entries:
        return []
    usable = 1.0 - 2.0 * _NOTE_PAGE_MARGIN
    width_pt = page_width_pt * usable
    line_height = _NOTE_PAGE_LINE_HEIGHT_PT / page_height_pt
    capacity = max(1, int(usable / line_height))
    heading_lines = min(_wrapped_line_count(heading, width_pt), capacity - 1) if capacity > 1 else 0
    body_capacity = capacity - heading_lines
    return [
        _note_page_marks(
            heading=heading if heading_lines else None,
            heading_lines=heading_lines,
            lines=lines,
            width=usable,
            line_height=line_height,
        )
        for lines in _paginate(entries, width_pt=width_pt, body_capacity=body_capacity)
    ]


def _paginate(
    entries: Sequence[NoteEntry], *, width_pt: float, body_capacity: int
) -> list[list[tuple[str, int]]]:
    """``entries`` grouped into pages of at most ``body_capacity`` wrapped
    lines, each line paired with the number of them it takes.

    A note never straddles a page boundary while a whole one would still fit
    on the next page: reading half a sentence, turning the sheet over and
    reading the rest is exactly the reading cost this change exists to
    avoid. The exception is a note that cannot fit on an *empty* page at all
    -- only reachable on a page far smaller than any answer sheet, since an
    A4 note page holds about sixty lines and `models.MAX_COMMENT_CHARS` caps
    one note at four. That one is sliced into page-sized pieces rather than
    cut short: `_chars_per_line` times ``body_capacity`` is, by the same
    over-estimate, a character count guaranteed to fit.
    """
    slice_size = _chars_per_line(width_pt) * body_capacity
    pages: list[list[tuple[str, int]]] = []
    current: list[tuple[str, int]] = []
    used = 0
    for entry in entries:
        text = _note_entry_line(entry)
        for start in range(0, len(text), slice_size):
            piece = text[start : start + slice_size]
            needed = _wrapped_line_count(piece, width_pt)
            if current and used + needed > body_capacity:
                pages.append(current)
                current, used = [], 0
            current.append((piece, needed))
            used += needed
    if current:
        pages.append(current)
    return pages


def _note_page_marks(
    *,
    heading: str | None,
    heading_lines: int,
    lines: Sequence[tuple[str, int]],
    width: float,
    line_height: float,
) -> tuple[AnnotationMark, ...]:
    """One note page's marks, stacked from its top margin downwards.

    Every line gets its own rect, for the reason `_stacked_rects` gives
    every band note one: `PdfEngine.render_annotations` draws each mark from
    its own top-left corner, so a single joined string would be re-wrapped
    and re-shrunk as one block, and one long note could push the rest off
    the bottom of the page.
    """
    marks: list[AnnotationMark] = []
    top = _NOTE_PAGE_MARGIN
    if heading is not None:
        marks.append(
            AnnotationMark(
                kind=AnnotationKind.COMMENT,
                rect=NormalizedRect(
                    x=_NOTE_PAGE_MARGIN, y=top, width=width, height=heading_lines * line_height
                ),
                text=heading,
            )
        )
        top += heading_lines * line_height
    for text, needed in lines:
        marks.append(
            AnnotationMark(
                kind=AnnotationKind.COMMENT,
                rect=NormalizedRect(
                    x=_NOTE_PAGE_MARGIN, y=top, width=width, height=needed * line_height
                ),
                text=text,
            )
        )
        top += needed * line_height
    return tuple(marks)


def build_export_marks(
    *,
    question: Question,
    grade: GradeResult,
    annotations: Sequence[Annotation],
    recognitions: Sequence[RecognitionResult],
    fallback_score_area: NormalizedRect | None = None,
) -> QuestionExport:
    """The resolved marks to draw for one question's
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
    has none -- and contributes only its note line. A line whose annotation
    could not be placed says so (`_UNPLACED_SUFFIX`), so an unplaced mark is
    visibly unplaced rather than absent. Each note gets its own
    slice of the band rather than every note sharing one rect: marks are
    drawn independently from their own top-left corner, so two notes on one
    rect would land on top of one another, both illegible, while the export
    still reported success (P2 review, round 5).

    **Where the notes go when there is no band** (Issue #161). A question
    with no ``comment_area`` -- since Issue #161 that is every question
    registered by detection, because the band used to be derived from the
    answer box and was measured sitting on the student's own writing -- has
    its notes handed back in `QuestionExport.unplaced_notes` instead of
    drawn. `build_note_pages` puts them on an appended page. They are
    deliberately *not* dropped and *not* squeezed into the score's margin
    strip: dropping is Issue #121's failure, and the strip is three
    characters wide, so prose in it is an ellipsis with a few words in front
    of it.
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
                text=_fallback_score_text(question, grade),
            )
        )
    notes: list[str] = []
    for annotation in attempt_annotations:
        # Its text and its rect would both be this mark's (§2.1: the number
        # comes from the confirmed grade, the position from `score_area`),
        # so drawing it too would just stack the same string on itself.
        if annotation.kind is AnnotationKind.SCORE:
            continue
        rects = resolve_annotation_rects(
            annotation, question=question, recognitions=attempt_recognitions
        )
        if rects is not None and annotation.kind is not AnnotationKind.COMMENT:
            marks.extend(AnnotationMark(kind=annotation.kind, rect=rect) for rect in rects)
        note = _note_text(annotation, placed=rects is not None)
        if note is not None:
            notes.append(note)
    if question.comment_area is None:
        return QuestionExport(marks=tuple(marks), unplaced_notes=tuple(notes))
    marks.extend(_note_marks(question.comment_area, notes))
    return QuestionExport(marks=tuple(marks), unplaced_notes=())


__all__ = [
    "NoteEntry",
    "QuestionExport",
    "ReexportDecision",
    "build_export_marks",
    "build_note_pages",
    "decide_reexport",
    "fallback_score_areas",
    "note_page_heading",
    "review_version_snapshot",
    "unconfirmed_question_ids",
    "unplaceable_question_ids",
]
