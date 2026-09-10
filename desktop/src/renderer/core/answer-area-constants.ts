/**
 * Sentinel label the sidecar uses for a detected box it could not attribute
 * to any question. Duplicated here rather than derived from the API: it is a
 * value the two sides agree on, not part of any schema the generator produces.
 */
export const UNASSIGNED_QUESTION_LABEL = "__unassigned__";

/** Shown wherever {@link UNASSIGNED_QUESTION_LABEL} would otherwise appear. */
export const UNASSIGNED_QUESTION_DISPLAY_LABEL = "設問未割当";

/** Smallest box a drag may produce, as a fraction of the page. */
export const MINIMUM_BOX_SIZE = 0.01;

/** Widest a page is drawn in CSS pixels. */
export const MAX_PAGE_WIDTH_PX = 720;
