import type { JSX } from "react";

import type { HomeDashboard } from "../../core/home-dashboard.js";
import {
  HomeWorkBucket,
  homeWorkBucketMeta,
} from "../../core/submission-work-bucket.js";
import { HomeBarChart } from "./charts/HomeBarChart.js";
import {
  KPI_NUMBER_INDENT_STYLE,
  KPI_VALUE_STYLE,
  NUMERIC_STYLE,
  PANEL_TITLE_STYLE,
  toneDotClass,
} from "./home-format.js";

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
      className="flex h-full min-w-0 flex-col rounded-xl bg-surface-container p-xl"
    >
      <div className="flex items-center justify-between gap-md">
        <h2 className="font-semibold text-heading" style={PANEL_TITLE_STYLE}>
          全体の進捗
        </h2>
        <span className="text-ui-label text-on-surface-variant">直近7日</span>
      </div>
      {/* Issue 360: the mock's four KPI columns span ~88% of the card at a
          ~128px pitch. A quarter-width grid reproduces that, where the old
          label-hugging flex left ~49% of the card empty. Issue 366 item 3:
          the mock rules the columns apart. Issue 371 item 8: that rule is the
          number block's 50px, not the 82px full cell a border filled, so it is
          a 1px mark (like the chart strokes) rather than a cell border. */}
      <dl className="mt-lg grid grid-cols-2 gap-x-md gap-y-lg sm:grid-cols-4">
        {STAT_BUCKETS.map(({ bucket, tone }, index) => (
          <div key={bucket} className="relative flex flex-col gap-xs">
            {index > 0 ? (
              <span
                aria-hidden
                data-testid={`home-kpi-rule-${bucket}`}
                className={`absolute bottom-0 -left-xs h-kpi-rule w-px bg-chart-divider ${
                  index % 2 === 1 ? "block" : "hidden sm:block"
                }`}
              />
            ) : null}
            <dt className="flex items-center gap-sm text-ui-label text-on-surface-variant">
              <span
                aria-hidden
                className={`size-4 shrink-0 rounded-full ${toneDotClass(tone)}`}
              />
              {homeWorkBucketMeta(bucket).label}
            </dt>
            <dd
              data-testid={`home-bucket-${bucket}`}
              className="font-semibold text-on-surface"
              style={{
                ...NUMERIC_STYLE,
                ...KPI_VALUE_STYLE,
                ...KPI_NUMBER_INDENT_STYLE,
              }}
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
      {/* The mock goes straight from the KPIs to the bars; the old
          「日別の取込」sub-heading and its rule added a fourth type size and
          broke the card's spacing rhythm (Issue 353, parent 333 §5). */}
      <div className="mt-lg flex min-h-0 flex-1 flex-col">
        <HomeBarChart points={daily} />
      </div>
    </section>
  );
}
