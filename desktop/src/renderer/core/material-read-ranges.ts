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
