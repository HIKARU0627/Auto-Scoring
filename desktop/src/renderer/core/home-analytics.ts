/**
 * Aggregations the home dashboard draws but does not fetch (Issue #336).
 *
 * Everything here is derived from the rows the loader already read, so the
 * dashboard can show a chart without a new backend endpoint (`docs/home-dashboard.md`
 * §4). The functions take the data as arguments -- no `Date.now()`, no client --
 * so the same input always produces the same chart and a test can pin both the
 * number of bars and their heights.
 */
import type { SubmissionResponse } from "./home-dashboard.js";
import { HomeWorkBucket, homeWorkBucketOf } from "./submission-work-bucket.js";

/** How many days the daily bar chart shows. The mock shows 7. */
export const HOME_DAILY_DAYS = 7;

export interface HomeDailyPoint {
  /** `YYYY-M-D` local key, used only to group submissions. */
  readonly key: string;
  /** Short axis label, e.g. `9/4`. */
  readonly label: string;
  readonly count: number;
  /**
   * Submissions of that day whose work is confirmed (`reviewed` / `exported`).
   * The mock's bar is two stacked series, so the chart needs the split; it is
   * read from the same `submission.state` the buckets use, never guessed.
   */
  readonly doneCount: number;
}

function localDayKey(date: Date): string {
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

/**
 * Counts submissions per local calendar day for the last `days` days, oldest
 * first. Days with no submissions stay in the list with `count: 0`, so the bar
 * chart always has one bar per day instead of silently dropping empty days.
 */
export function dailySubmissionCounts(
  submissions: readonly SubmissionResponse[],
  now: Date,
  days: number = HOME_DAILY_DAYS,
): readonly HomeDailyPoint[] {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);

  const points: HomeDailyPoint[] = [];
  const byKey = new Map<
    string,
    { key: string; label: string; count: number; doneCount: number }
  >();
  for (let offset = days - 1; offset >= 0; offset -= 1) {
    const date = new Date(start);
    date.setDate(start.getDate() - offset);
    const point = {
      key: localDayKey(date),
      label: `${date.getMonth() + 1}/${date.getDate()}`,
      count: 0,
      doneCount: 0,
    };
    points.push(point);
    byKey.set(point.key, point);
  }

  for (const submission of submissions) {
    const created = new Date(submission.created_at);
    if (Number.isNaN(created.getTime())) {
      continue;
    }
    const point = byKey.get(localDayKey(created));
    if (point !== undefined) {
      point.count += 1;
      if (homeWorkBucketOf(submission.state) === HomeWorkBucket.done) {
        point.doneCount += 1;
      }
    }
  }

  return points;
}

/** A "nice" number is `mantissa * 10^n` with a mantissa in `{1, 2, 5}`. */
const NICE_MANTISSAS = [1, 2, 5] as const;

/** The largest value of the form `{1,2,5} * 10^n` not above `limit`, or 0. */
function largestNiceValueWithin(limit: number): number {
  let best = 0;
  for (let scale = 1; scale <= limit; scale *= 10) {
    for (const mantissa of NICE_MANTISSAS) {
      const candidate = mantissa * scale;
      if (candidate <= limit) {
        best = candidate;
      }
    }
  }
  return best;
}

export interface HomeBarAxis {
  /** y-axis upper bound: an integer multiple of `step`, strictly above the data. */
  readonly upper: number;
  /** The `{1,2,5} * 10^n` interval the upper bound is a multiple of (min 1). */
  readonly step: number;
  /** Labeled tick values from 0 to `upper`, thinned to at most 6 labels. */
  readonly ticks: readonly number[];
}

/**
 * y-axis headroom for the home daily bar chart (Issue #382).
 *
 * The axis used to end exactly at the tallest bar (`domain={[0, "dataMax"]}`),
 * so the bar touched the top of the plot. Pick a "nice" upper bound instead --
 * a multiple of `{1,2,5} * 10^n` -- with at least 10% of the plot left empty,
 * and put the labeled ticks on that same bound so a label never disagrees with
 * a bar height.
 *
 * The invariants, in order of importance:
 * - `upper > max`, so the tallest bar never touches the ceiling.
 * - `max / upper <= 0.90`, so there is always visible headroom.
 * - `max / upper >= 0.70` once `max >= 10`: the bound is not allowed to drift
 *   so far up that the bars look short. Below 10 this cannot hold with an
 *   integer upper bound (the {1,2,5} values are too far apart), so it is not
 *   promised there; that is the shape of the spec, not a defect.
 * - `upper` is an integer multiple of a `{1,2,5} * 10^n` step (min 1).
 */
export function homeBarAxis(maxCount: number): HomeBarAxis {
  if (!Number.isFinite(maxCount) || maxCount <= 0) {
    return { upper: 1, step: 1, ticks: [0, 1] };
  }
  // Aim for the top bar to fill 90% of the plot; `* 10 / 9` keeps exact
  // multiples exact instead of paying `0.9`'s binary rounding.
  const target = (maxCount * 10) / 9;
  const step = Math.max(1, largestNiceValueWithin(target / 4));
  const ratio = target / step;
  const whole = Math.round(ratio);
  const intervals = Math.abs(ratio - whole) < 1e-9 ? whole : Math.ceil(ratio);
  const upper = step * intervals;

  // `step` is chosen at roughly a quarter of the target, so there are 4-10
  // intervals; a stride of 2 caps the labels at 6 without moving `upper`.
  const stride = intervals <= 5 ? 1 : 2;
  const ticks: number[] = [];
  for (let value = 0; value < upper; value += stride * step) {
    ticks.push(value);
  }
  ticks.push(upper);
  return { upper, step, ticks };
}

/** `YYYY/MM/DD` in local time, the format every home date uses. */
export function formatHomeDate(iso: string | null | undefined): string {
  if (iso === null || iso === undefined) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}/${month}/${day}`;
}

/** The most recent of a set of ISO timestamps, or `null` when there are none. */
export function latestTimestamp(
  candidates: readonly (string | null | undefined)[],
): string | null {
  let latest: string | null = null;
  let latestMs = Number.NEGATIVE_INFINITY;
  for (const candidate of candidates) {
    if (candidate === null || candidate === undefined) {
      continue;
    }
    const ms = Date.parse(candidate);
    if (!Number.isNaN(ms) && ms > latestMs) {
      latest = candidate;
      latestMs = ms;
    }
  }
  return latest;
}
