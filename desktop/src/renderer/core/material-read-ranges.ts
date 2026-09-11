/** Fraction of row height — same tolerance at any reflow (Issue #85). */
export const MATERIAL_COVER_EPSILON = 0.001;

export type MaterialRange = readonly [number, number];

export function mergeMaterialRange(
  ranges: readonly MaterialRange[],
  start: number,
  end: number,
): MaterialRange[] {
  const merged: MaterialRange[] = [];
  let lower = start;
  let upper = end;
  let placed = false;
  for (const range of ranges) {
    if (placed) {
      merged.push(range);
    } else if (range[1] < lower - MATERIAL_COVER_EPSILON) {
      merged.push(range);
    } else if (range[0] > upper + MATERIAL_COVER_EPSILON) {
      merged.push([lower, upper]);
      placed = true;
      merged.push(range);
    } else {
      lower = Math.min(lower, range[0]);
      upper = Math.max(upper, range[1]);
    }
  }
  if (!placed) {
    merged.push([lower, upper]);
  }
  merged.sort((a, b) => a[0] - b[0]);
  return merged;
}

export function sameMaterialRanges(
  a: readonly MaterialRange[],
  b: readonly MaterialRange[],
): boolean {
  if (a.length !== b.length) {
    return false;
  }
  for (let i = 0; i < a.length; i += 1) {
    const left = a[i];
    const right = b[i];
    if (left == null || right == null) {
      return false;
    }
    if (left[0] !== right[0] || left[1] !== right[1]) {
      return false;
    }
  }
  return true;
}

export function materialRowIsCovered(
  ranges: readonly MaterialRange[] | null | undefined,
): boolean {
  if (ranges == null || ranges.length !== 1) {
    return false;
  }
  const first = ranges[0];
  if (first == null) {
    return false;
  }
  const [start, end] = first;
  return start <= MATERIAL_COVER_EPSILON && end >= 1 - MATERIAL_COVER_EPSILON;
}

/**
 * Where the first not-yet-covered part of a row begins, as a fraction of the
 * row's height, or `null` when the row is covered end to end.
 *
 * A tall row seen only from its top has its gap *below* the viewport even
 * though the row's own top has scrolled above it, so `rowTop < containerTop`
 * cannot tell which way the remaining material lies. The fraction can
 * (`_firstGapY` in the Flutter original).
 */
export function materialRowGapStart(
  ranges: readonly MaterialRange[] | null | undefined,
): number | null {
  if (ranges == null || ranges.length === 0) {
    return 0;
  }
  const first = ranges[0];
  if (first == null) {
    return 0;
  }
  if (
    first[0] <= MATERIAL_COVER_EPSILON &&
    first[1] >= 1 - MATERIAL_COVER_EPSILON
  ) {
    return null;
  }
  return first[0] > MATERIAL_COVER_EPSILON ? 0 : first[1];
}

/**
 * How far inside the viewport the unread point is aimed, in CSS pixels.
 *
 * Aiming it exactly at the top edge is what a naive `scrollIntoView` does, but
 * the browser rounds the scroll offset to a device pixel. The measured
 * container landed the first unread row 0.56px above the top edge, so the gate
 * recorded the leading 0.4% of the row as still unread; pressing again tried to
 * scroll up by that fraction and the browser refused, stalling forever. Aiming
 * a pixel *inside* the edge survives the rounding without weakening the gate:
 * anything genuinely unread is still off the visible range.
 */
export const MATERIAL_REVEAL_EDGE_MARGIN_PX = 1;

export interface MaterialRevealInput {
  readonly scrollTop: number;
  readonly maxScrollTop: number;
  readonly viewportHeight: number;
  /**
   * Viewport-space y of the first not-yet-read point of the first unread row
   * (`rowTop + gapStart * rowHeight`). Independently of which way it lies, the
   * target below brings that point just inside the top of the viewport.
   */
  readonly unreadTop: number;
  /** Viewport-space y of the scroll container's own top edge. */
  readonly containerTop: number;
}

export interface MaterialRevealPlan {
  readonly scrollTop: number;
  /**
   * False only when the container cannot move at all (no scroll range), which
   * the caller must surface instead of silently pretending to have revealed
   * anything (Issue #328, decision 2).
   */
  readonly moved: boolean;
}

/**
 * Where to put the scroll container so the first unread row comes into view,
 * rather than paging by whole viewports (Issue #328).
 *
 * Relative viewport paging (`scrollBy({ top: ±clientHeight })`) is not
 * guaranteed to accumulate: on the measured container it moved to one page and
 * then no-ops, leaving the unread rows off-screen and 承認 permanently
 * disabled. Aiming at the unread point itself both guarantees the direction
 * (#319) and guarantees that each press gets closer. The point is its own
 * fraction of the row, so a row taller than the viewport also advances.
 *
 * When the unread point is already at the top, aligning to it would be a
 * no-op, so advance one viewport; if even that is impossible the container has
 * no scroll range and `moved` is false.
 */
export function planMaterialReveal(
  input: MaterialRevealInput,
): MaterialRevealPlan {
  const limit = Math.max(input.maxScrollTop, 0);
  const clamp = (value: number) => Math.min(Math.max(value, 0), limit);
  const aligned = clamp(
    input.scrollTop +
      (input.unreadTop - input.containerTop) -
      MATERIAL_REVEAL_EDGE_MARGIN_PX,
  );
  if (aligned !== input.scrollTop) {
    return { scrollTop: aligned, moved: true };
  }
  const down = clamp(input.scrollTop + input.viewportHeight);
  if (down !== input.scrollTop) {
    return { scrollTop: down, moved: true };
  }
  const up = clamp(input.scrollTop - input.viewportHeight);
  if (up !== input.scrollTop) {
    return { scrollTop: up, moved: true };
  }
  return { scrollTop: input.scrollTop, moved: false };
}
