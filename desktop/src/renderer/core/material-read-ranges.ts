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
