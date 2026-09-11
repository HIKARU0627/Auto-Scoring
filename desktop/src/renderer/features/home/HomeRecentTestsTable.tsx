import type { JSX } from "react";
import { ChevronRight } from "lucide-react";

import {
  AppRoutes,
  pdfReview,
  submissionQueue,
  testSettings,
} from "../../core/app-routes.js";
import {
  type HomeDashboard,
  type HomeTestProgress,
} from "../../core/home-dashboard.js";
import { formatHomeDate } from "../../core/home-analytics.js";
import {
  HOME_WORK_BUCKET_ORDER,
  HomeWorkBucket,
  homeWorkBucketMeta,
} from "../../core/submission-work-bucket.js";
import {
  NUMERIC_STYLE,
  PANEL_TITLE_STYLE,
  statusPillClass,
  TABLE_HEAD_STYLE,
} from "./home-format.js";

/**
 * 最近のテスト table (Issue #336): name / status pill / answer count /
 * question-level progress / last update. `home-test-card-<id>` and
 * `home-open-queue-<id>` are kept from the old card list because E2E and the
 * frontend invariants (INV-149/INV-150) depend on them.
 */
export function HomeRecentTestsTable({
  dashboard,
  onOpen,
}: {
  dashboard: HomeDashboard;
  onOpen: (route: string) => void;
}): JSX.Element {
  return (
    <section
      data-testid="home-recent-tests"
      className="min-w-0 rounded-xl bg-surface-container p-xl"
    >
      <div className="flex items-center justify-between gap-md">
        <h2 className="font-semibold text-on-surface" style={PANEL_TITLE_STYLE}>
          最近のテスト
        </h2>
        <div className="flex shrink-0 items-center gap-lg">
          {/* The overflow count is real data (151); the mock always shows the
              plain destination link, so both live here (Issue 360). */}
          {dashboard.hiddenTestCount > 0 ? (
            <button
              type="button"
              data-testid="home-open-hidden-tests"
              onClick={() => {
                onOpen(AppRoutes.testList);
              }}
              className="rounded-sm text-ui-label text-on-surface-variant hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
            >
              他{dashboard.hiddenTestCount}件を見る
            </button>
          ) : null}
          <button
            type="button"
            data-testid="home-open-all-tests"
            onClick={() => {
              onOpen(AppRoutes.testList);
            }}
            className="rounded-sm text-ui-label text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          >
            すべて見る
          </button>
        </div>
      </div>
      {/* table-fixed + explicit column widths (Issue 360): the old
          label-hugging auto layout gave the name only ~100px (the mock is
          ~200px) while the 進捗 column held 158px of slack. */}
      <div className="mt-md overflow-x-auto">
        <table
          className="w-full table-fixed border-collapse text-left text-body-medium"
          style={{ minWidth: "40rem" }}
        >
          <thead>
            <tr
              className="text-ui-label text-on-surface-variant"
              style={TABLE_HEAD_STYLE}
            >
              <th scope="col" className="w-1/4 py-sm pr-md font-normal">
                テスト名
              </th>
              <th scope="col" className="w-1/6 py-sm pr-md font-normal">
                状態
              </th>
              <th
                scope="col"
                className="w-16 py-sm pr-md text-right font-normal"
              >
                答案数
              </th>
              <th scope="col" className="w-1/3 py-sm pr-md font-normal">
                進捗
              </th>
              <th scope="col" className="w-20 py-sm font-normal">
                最終更新
              </th>
              <th scope="col" className="w-10 py-sm font-normal">
                <span className="sr-only">開く</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {dashboard.visibleTests.map((progress) => (
              <TestRow
                key={progress.test.id}
                progress={progress}
                onOpen={onOpen}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TestRow({
  progress,
  onOpen,
}: {
  progress: HomeTestProgress;
  onOpen: (route: string) => void;
}): JSX.Element {
  const test = progress.test;
  return (
    <tr
      data-testid={`home-test-card-${test.id}`}
      className="border-t border-outline-variant align-top"
    >
      <th scope="row" className="py-md pr-md font-medium">
        <span
          data-testid={`home-test-name-${test.id}`}
          className="block truncate text-on-surface"
          title={test.name}
        >
          {test.name}
        </span>
      </th>
      {/* Secondary state detail moves out of the name cell into this column so
          no row stacks name / counts / link (Issue 360). */}
      <td className="py-md pr-md">
        <span
          data-testid={`home-test-status-${test.id}`}
          className={`inline-flex rounded-full px-sm py-xs text-ui-label ${statusPillClass(progress.statusBadge)}`}
        >
          {progress.statusBadge.label}
        </span>
        <BucketCounts progress={progress} />
      </td>
      <td
        className="py-md pr-md text-right text-on-surface"
        style={NUMERIC_STYLE}
      >
        {progress.answerCount ?? "—"}
      </td>
      <td className="py-md pr-md">
        <ProgressCell progress={progress} onOpen={onOpen} />
      </td>
      <td className="py-md text-on-surface-variant" style={NUMERIC_STYLE}>
        {formatHomeDate(progress.lastUpdatedAt)}
      </td>
      <td className="py-md pl-sm text-right">
        <RowChevron progress={progress} onOpen={onOpen} />
      </td>
    </tr>
  );
}

function ProgressCell({
  progress,
  onOpen,
}: {
  progress: HomeTestProgress;
  onOpen: (route: string) => void;
}): JSX.Element {
  const test = progress.test;
  const summary = progress.reviewSummary;
  const percent = progress.reviewPercent;

  if (progress.answerCount === null) {
    return (
      <span
        data-testid={`home-test-progress-unavailable-${test.id}`}
        className="text-ui-label text-on-surface-variant"
      >
        答案を取得できませんでした
      </span>
    );
  }

  // Issue 360: one line only. The old stacked form put the queue link above
  // the bar and % (41px of ink / two lines); the mock keeps all three inline.
  return (
    <div className="flex min-w-0 items-center gap-sm whitespace-nowrap">
      <button
        type="button"
        data-testid={`home-open-queue-${test.id}`}
        onClick={() => {
          onOpen(submissionQueue(test.id));
        }}
        className="shrink-0 rounded-sm text-ui-label text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        確認済み {progress.doneCount} / {progress.total}
      </button>
      {summary !== null && percent !== null ? (
        <>
          {/* The track uses --color-progress-track (L+17 over the card); the
              old surface-container-high sat only L+6 away and vanished on 0%
              rows (Issue 360). */}
          <div
            role="progressbar"
            data-testid={`home-test-progress-${test.id}`}
            aria-label={`${test.name} の確認済み設問`}
            aria-valuemin={0}
            aria-valuemax={summary.total}
            aria-valuenow={summary.confirmed}
            className="h-2 w-14 shrink-0 rounded-sm bg-progress-track"
          >
            <div
              data-testid={`home-test-progress-fill-${test.id}`}
              className="h-full rounded-sm bg-primary"
              style={{ width: `${percent}%` }}
            />
          </div>
          <span
            data-testid={`home-test-progress-percent-${test.id}`}
            className="w-9 shrink-0 text-right text-ui-label text-on-surface-variant"
            style={NUMERIC_STYLE}
          >
            {percent}%
          </span>
        </>
      ) : (
        <span
          data-testid={`home-test-progress-unavailable-${test.id}`}
          className="truncate text-ui-label text-on-surface-variant"
        >
          設問の進捗を取得できませんでした
        </span>
      )}
    </div>
  );
}

/**
 * The row-end `›` from the mock (Issue 360) doubles as the "continue where I
 * left off" entry point: `home-resume-registration-<id>` and
 * `home-resume-review-<id>` are depended on by the E2E specs and the
 * must-not-break list in Issue #336, and their old inline label was being
 * truncated mid-word. The full label stays as the accessible name/tooltip;
 * a row with nothing to resume still shows the same chevron as the mock.
 */
function RowChevron({
  progress,
  onOpen,
}: {
  progress: HomeTestProgress;
  onOpen: (route: string) => void;
}): JSX.Element {
  const test = progress.test;
  if (progress.isDraft) {
    return (
      <button
        type="button"
        data-testid={`home-resume-registration-${test.id}`}
        onClick={() => {
          onOpen(testSettings(test.id));
        }}
        aria-label="登録を続ける"
        title="登録を続ける"
        className="inline-flex rounded-sm text-on-surface-variant hover:text-on-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        <ChevronRight aria-hidden size={18} />
      </button>
    );
  }

  const resumable = progress.resumableSubmission;
  if (resumable === null) {
    return (
      <ChevronRight aria-hidden size={18} className="text-on-surface-variant" />
    );
  }
  const label =
    resumable.student_label === null || resumable.student_label === undefined
      ? "レビューを続ける"
      : `レビューを続ける（${resumable.student_label}）`;
  return (
    <button
      type="button"
      data-testid={`home-resume-review-${test.id}`}
      onClick={() => {
        onOpen(pdfReview(test.id, resumable.id));
      }}
      aria-label={label}
      title={label}
      className="inline-flex rounded-sm text-on-surface-variant hover:text-on-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
    >
      <ChevronRight aria-hidden size={18} />
    </button>
  );
}

function BucketCounts({
  progress,
}: {
  progress: HomeTestProgress;
}): JSX.Element | null {
  const shown = HOME_WORK_BUCKET_ORDER.flatMap((bucket) => {
    if (bucket === HomeWorkBucket.done) {
      return [];
    }
    const count = progress.countOf(bucket);
    if (count === 0) {
      return [];
    }
    const meta = homeWorkBucketMeta(bucket);
    return [{ bucket, count, label: meta.label }];
  });

  if (shown.length === 0) {
    return null;
  }

  return (
    <span className="mt-xs flex flex-wrap gap-sm text-ui-label text-on-surface-variant">
      {shown.map(({ bucket, label, count }) => (
        <span key={bucket}>
          {label} {count}件
        </span>
      ))}
    </span>
  );
}
