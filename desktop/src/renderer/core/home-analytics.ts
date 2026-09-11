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
