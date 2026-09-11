import type { JSX } from "react";

import type { HomeDashboard } from "../../core/home-dashboard.js";
import {
  HomeWorkBucket,
  homeWorkBucketMeta,
} from "../../core/submission-work-bucket.js";
import { HomeBarChart } from "./charts/HomeBarChart.js";
import { NUMERIC_STYLE, toneDotClass } from "./home-format.js";

const STAT_BUCKETS = [
  { bucket: HomeWorkBucket.needsReview, tone: "attention" },
  { bucket: HomeWorkBucket.intakeDone, tone: "primary" },
  { bucket: HomeWorkBucket.processing, tone: "info" },
  { bucket: HomeWorkBucket.done, tone: "success" },
] as const;

/**
 * 全体の進捗 panel (Issue #336): the four answer buckets and the daily bar
 * chart. The failed bucket is only drawn when it is non-zero -- hiding an
 * import failure behind a zero would be the lie #333 §4 forbids.
 */
export function HomeProgressPanel({
  dashboard,
}: {
  dashboard: HomeDashboard;
}): JSX.Element {
  const failedCount = dashboard.count(HomeWorkBucket.failed);
  const daily = dashboard.dailySubmissions();
  return (
    <section
      data-testid="home-progress-panel"
      className="min-w-0 rounded-xl bg-surface-container p-lg"
    >
      <div className="flex items-center justify-between gap-md">
        <h2 className="text-body-medium font-semibold text-on-surface">
          全体の進捗
        </h2>
        <span className="text-ui-label text-on-surface-variant">直近7日</span>
      </div>
      <dl className="mt-lg grid grid-cols-2 gap-md sm:grid-cols-4">
        {STAT_BUCKETS.map(({ bucket, tone }) => (
          <div key={bucket} className="flex flex-col gap-xs">
            <dt className="flex items-center gap-sm text-ui-label text-on-surface-variant">
              <span
                aria-hidden
                className={`size-3 shrink-0 rounded-full ${toneDotClass(tone)}`}
              />
              {homeWorkBucketMeta(bucket).label}
            </dt>
            <dd
              data-testid={`home-bucket-${bucket}`}
              className="text-score font-semibold text-on-surface"
              style={NUMERIC_STYLE}
            >
              {dashboard.count(bucket)}
            </dd>
          </div>
        ))}
      </dl>
      {failedCount > 0 ? (
        <p
          data-testid="home-bucket-failed"
          className="mt-md flex items-center gap-sm rounded-md bg-error-container px-md py-sm text-ui-label text-on-error-container"
        >
          <span aria-hidden className="size-3 rounded-full bg-error" />
          {homeWorkBucketMeta(HomeWorkBucket.failed).label}
          <span data-testid="home-bucket-failed-count" style={NUMERIC_STYLE}>
            {failedCount}
          </span>
          件。答案取込画面でやり直せます。
        </p>
      ) : null}
      <div className="mt-lg border-t border-outline-variant pt-lg">
        <h3 className="text-ui-label text-on-surface-variant">日別の取込</h3>
        <div className="mt-sm">
          <HomeBarChart points={daily} />
        </div>
      </div>
    </section>
  );
}
