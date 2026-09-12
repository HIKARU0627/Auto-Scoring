import type { components } from "../api/generated/schema.js";
import type { NormalizedRect } from "./pdf-review-geometry.js";

export type QuestionScorePlacement =
  components["schemas"]["QuestionScorePlacementResponse"];

/**
 * The score a question's confirmed grade draws on the exported sheet, and the
 * page-normalized rect it goes in (Issue #406).
 *
 * The placement itself is **not computed here**. `QuestionResponse.
 * score_placement` is filled by the sidecar from
 * `domain.pdf_export.score_placements`, the same judgment the export gate and
 * renderer use, so the screen and the paper can only disagree if the sidecar
 * itself does. This module only turns that judgment plus the grade the screen
 * already shows into the text and box the overlay needs -- mirroring
 * `domain.pdf_export.build_export_marks` (`own` draws `a/m`, the margin strip
 * draws `a/m 問N`).
 */
/** The three `ScorePlacementTarget` wire values. */
export const SCORE_PLACEMENT_OWN = "own";
export const SCORE_PLACEMENT_MARGIN = "margin";
export const SCORE_PLACEMENT_NONE = "none";

export interface ScoreOverlay {
  readonly rect: NormalizedRect;
  readonly text: string;
  /** `"own"` or `"margin"` — never `"none"` (there would be no overlay). */
  readonly placement:
    typeof SCORE_PLACEMENT_OWN | typeof SCORE_PLACEMENT_MARGIN;
}

export function scoreOverlay(input: {
  readonly placement: QuestionScorePlacement | null | undefined;
  readonly grade:
    | { readonly score: { readonly awarded: number; readonly maximum: number } }
    | null
    | undefined;
  /** The question's stored `number`, verbatim: the margin line names it the
   *  same way the export does (`_fallback_score_text`). */
  readonly questionNumber: string;
}): ScoreOverlay | null {
  const { placement, grade } = input;
  if (placement == null || grade == null || placement.rect == null) {
    return null;
  }
  if (placement.target === SCORE_PLACEMENT_NONE) {
    return null;
  }
  const score = `${grade.score.awarded}/${grade.score.maximum}`;
  const margin = placement.target === SCORE_PLACEMENT_MARGIN;
  return {
    rect: placement.rect,
    text: margin ? `${score} ${input.questionNumber}` : score,
    placement: margin ? SCORE_PLACEMENT_MARGIN : SCORE_PLACEMENT_OWN,
  };
}

/**
 * Whether the export will refuse this submission because this question's score
 * has nowhere to go (`ScorePlacementTarget.NONE`, `no_room_for_score`).
 *
 * Reading the sidecar's value rather than re-deriving it is the whole point of
 * Issue #406: the two functions that decide it (`fallback_score_areas` /
 * `unplaceable_question_ids`) are not reimplemented on this side, so the screen
 * cannot promise a placement the export will not honour.
 */
export function hasNoRoomForScore(
  placement: QuestionScorePlacement | null | undefined,
): boolean {
  return placement?.target === SCORE_PLACEMENT_NONE;
}

/**
 * Where a question's annotation comments are written by the export (Issue
 * #406).
 *
 * `"band"` means a human placed an `ANNOTATION_AREA` region, and the notes go
 * into `comment_area`, exactly as before Issue #161. `"note-page"` is every
 * question registered by detection: its comments leave the answer sheet and go
 * to an appended note page (`build_note_pages`). The review screen draws no
 * comment text on the answer in either case -- since Issue #141 prose on the
 * answer was the defect, not the feature -- it only says where the prose lands.
 */
export type CommentDestination = "band" | "note-page";

export function commentDestination(
  commentArea: NormalizedRect | null | undefined,
): CommentDestination {
  return commentArea == null ? "note-page" : "band";
}

/**
 * The symbol the export puts at the head of a shape's note line
 * (`domain.pdf_export._KIND_SYMBOLS`), so a reader can tell which `×` on the
 * answer a sentence is about. `comment` has none -- it is prose, not a mark.
 */
export const ANNOTATION_NOTE_SYMBOLS: Readonly<Record<string, string>> = {
  circle: "○",
  cross: "×",
  triangle: "△",
  underline: "＿",
  box: "□",
};

/** Appended to a note whose mark could not be placed on the answer. */
export const ANNOTATION_UNPLACED_SUFFIX = "（位置特定できず）";

/**
 * One note line as the export writes it, split so the UI can render the
 * comment as its own text node (accessibility and `getByText` both want the
 * prose, not the whole reference line as one blob).
 *
 * The parts mirror `domain.pdf_export._note_text` and `_note_entry_line`
 * exactly:
 *
 * * `score` annotations produce no note at all (`build_export_marks` skips
 *   them -- the number comes from the confirmed grade instead);
 * * a shape kind carries its symbol, and `（位置特定できず）` when it was not
 *   placed, even with no comment;
 * * a shape kind that was placed and has no comment produces nothing;
 * * `reference` (`第N頁 問M`) is present only when the destination is the
 *   trailing note page. A question with a `comment_area` writes its notes into
 *   that band, where nothing needs the sheet reference.
 */
export interface AnnotationNote {
  readonly reference: string | null;
  readonly symbol: string | null;
  readonly text: string;
  readonly suffix: string;
}

export function annotationNote(input: {
  readonly kind: string;
  readonly comment: string | null | undefined;
  readonly placed: boolean;
  readonly page: number;
  readonly questionNumber: string;
  readonly destination: CommentDestination;
}): AnnotationNote | null {
  if (input.kind === "score") {
    return null;
  }
  const comment = (input.comment ?? "").trim();
  const symbol = ANNOTATION_NOTE_SYMBOLS[input.kind] ?? null;
  if (symbol == null) {
    return comment.length === 0
      ? null
      : noteParts(input, { symbol: null, comment, suffix: "" });
  }
  if (input.placed) {
    return comment.length === 0
      ? null
      : noteParts(input, { symbol, comment, suffix: "" });
  }
  return noteParts(input, {
    symbol,
    comment,
    suffix: ANNOTATION_UNPLACED_SUFFIX,
  });
}

function noteParts(
  input: {
    readonly page: number;
    readonly questionNumber: string;
    readonly destination: CommentDestination;
  },
  parts: {
    readonly symbol: string | null;
    readonly comment: string;
    readonly suffix: string;
  },
): AnnotationNote {
  return {
    reference:
      input.destination === "note-page"
        ? `第${input.page}頁 ${input.questionNumber}`
        : null,
    symbol: parts.symbol,
    text: parts.comment,
    suffix: parts.suffix,
  };
}
