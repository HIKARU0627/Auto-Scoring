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
import { NUMERIC_STYLE, statusPillClass } from "./home-format.js";

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
      className="min-w-0 rounded-xl bg-surface-container p-lg"
    >
      <div className="flex items-center justify-between gap-md">
        <h2 className="text-body-medium font-semibold text-on-surface">
          最近のテスト
        </h2>
        {dashboard.hiddenTestCount > 0 ? (
          <button
            type="button"
            data-testid="home-open-hidden-tests"
            onClick={() => {
              onOpen(AppRoutes.testList);
            }}
            className="shrink-0 rounded-sm text-ui-label text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          >
            他{dashboard.hiddenTestCount}件を見る
          </button>
        ) : null}
      </div>
      <div className="mt-md overflow-x-auto">
        <table
          className="w-full border-collapse text-left text-body-medium"
          style={{ minWidth: "40rem" }}
        >
          <thead>
            <tr className="text-ui-label text-on-surface-variant">
              <th scope="col" className="py-sm pr-md font-normal">
                テスト名
              </th>
              <th scope="col" className="py-sm pr-md font-normal">
                状態
              </th>
              <th scope="col" className="py-sm pr-md text-right font-normal">
                答案数
              </th>
              <th scope="col" className="py-sm pr-md font-normal">
                進捗
              </th>
              <th scope="col" className="py-sm font-normal">
                最終更新
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
      <th scope="row" className="max-w-xs py-md pr-md font-medium">
        <span
          data-testid={`home-test-name-${test.id}`}
          className="block truncate text-on-surface"
          title={test.name}
        >
          {test.name}
        </span>
        <BucketCounts progress={progress} />
        {resumeAction(progress, onOpen)}
      </th>
      <td className="py-md pr-md">
        <span
          data-testid={`home-test-status-${test.id}`}
          className={`inline-flex rounded-full px-sm py-xs text-ui-label ${statusPillClass(progress.statusBadge)}`}
        >
          {progress.statusBadge.label}
        </span>
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

  return (
    <div className="flex min-w-0 flex-col gap-xs">
      <button
        type="button"
        data-testid={`home-open-queue-${test.id}`}
        onClick={() => {
          onOpen(submissionQueue(test.id));
        }}
        className="inline-flex w-fit items-center gap-xs rounded-sm text-ui-label text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        確認済み {progress.doneCount} / {progress.total}
        <ChevronRight aria-hidden size={14} />
      </button>
      {summary !== null && percent !== null ? (
        <div className="flex items-center gap-sm">
          <div
            role="progressbar"
            data-testid={`home-test-progress-${test.id}`}
            aria-label={`${test.name} の確認済み設問`}
            aria-valuemin={0}
            aria-valuemax={summary.total}
            aria-valuenow={summary.confirmed}
            className="h-2 min-w-0 flex-1 rounded-sm bg-progress-track"
          >
            <div
              data-testid={`home-test-progress-fill-${test.id}`}
              className="h-full rounded-sm bg-primary"
              style={{ width: `${percent}%` }}
            />
          </div>
          <span
            data-testid={`home-test-progress-percent-${test.id}`}
            className="w-10 shrink-0 text-right text-ui-label text-on-surface-variant"
            style={NUMERIC_STYLE}
          >
            {percent}%
          </span>
        </div>
      ) : (
        <span
          data-testid={`home-test-progress-unavailable-${test.id}`}
          className="text-ui-label text-on-surface-variant"
        >
          設問の進捗を取得できませんでした
        </span>
      )}
    </div>
  );
}

/**
 * The two "continue where I left off" entry points. They are kept even though
 * the mock table has no such column: `home-resume-registration-<id>` and
 * `home-resume-review-<id>` are depended on by the E2E registration spec and
 * the must-not-break list in Issue #336.
 */
function resumeAction(
  progress: HomeTestProgress,
  onOpen: (route: string) => void,
): JSX.Element | null {
  const test = progress.test;
  if (progress.isDraft) {
    return (
      <button
        type="button"
        data-testid={`home-resume-registration-${test.id}`}
        onClick={() => {
          onOpen(testSettings(test.id));
        }}
        className="mt-xs block rounded-sm text-left text-ui-label text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        登録を続ける
      </button>
    );
  }

  const resumable = progress.resumableSubmission;
  if (resumable === null) {
    return null;
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
      className="mt-xs block max-w-full truncate rounded-sm text-left text-ui-label text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      title={label}
    >
      {label}
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
