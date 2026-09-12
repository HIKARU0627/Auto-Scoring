import { useEffect, useState, type JSX } from "react";
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
  STATUS_PILL_STYLE,
  statusPillClass,
  TABLE_COLUMN_WIDTH_STYLE,
  TABLE_HEAD_STYLE,
} from "./home-format.js";

/**
 * 最近のテスト (Issue #336): name / status pill / answer count /
 * question-level progress / last update. `home-test-card-<id>`,
 * `home-test-name-<id>` and `home-open-queue-<id>` are kept from the old card
 * list because E2E and the frontend invariants (INV-149/INV-150) depend on
 * them, and the narrow block layout keeps the same testids.
 *
 * Issue #372 (parent #333) folded the quick-action rail into the body, so this
 * table now spans the full page width. The old content-column widths
 * (`w-1/4` / `w-16` / `w-1/3` / `w-20` / `w-10`) left a ~380px hole between
 * 進捗 and 最終更新; the columns are redistributed and the 進捗 track fills its
 * cell instead of staying at a fixed 140px.
 *
 * Below `lg` the table is replaced by one block per test. At 700px the table
 * hid ~150px of columns (including 最終更新) behind a horizontal scrollbar whose
 * native thumb (`--color-scrollbar-thumb` = `--color-outline`) was the
 * brightest element on the page, and the 状態 auxiliary text touched the
 * answer count ("取込済み 1件1"). The block layout shows every column and has
 * no scroller.
 */

/**
 * The dashboard's `lg` breakpoint, mirrored in JS. jsdom does not evaluate CSS
 * media queries, so the component has to ask the window directly; the resize
 * listener is what the tests drive (`window.dispatchEvent(new Event("resize"))`).
 */
const NARROW_MAX_WIDTH = 1024;

function isNarrow(): boolean {
  return typeof window !== "undefined" && window.innerWidth < NARROW_MAX_WIDTH;
}

function useNarrowLayout(): boolean {
  const [narrow, setNarrow] = useState(isNarrow);
  useEffect(() => {
    const onResize = (): void => {
      setNarrow(isNarrow());
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
    };
  }, []);
  return narrow;
}

export function HomeRecentTestsTable({
  dashboard,
  onOpen,
}: {
  dashboard: HomeDashboard;
  onOpen: (route: string) => void;
}): JSX.Element {
  const narrow = useNarrowLayout();

  return (
    <section
      data-testid="home-recent-tests"
      className="min-w-0 rounded-xl bg-surface-container p-xl"
    >
      <div className="flex items-center justify-between gap-md">
        <h2 className="font-semibold text-heading" style={PANEL_TITLE_STYLE}>
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
            className="rounded-sm text-ui-label text-primary-text hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          >
            すべて見る
          </button>
        </div>
      </div>
      <div className="mt-md">
        {narrow ? (
          <TestBlockList dashboard={dashboard} onOpen={onOpen} />
        ) : (
          <TestsTable dashboard={dashboard} onOpen={onOpen} />
        )}
      </div>
    </section>
  );
}

/**
 * `table-fixed` with the Issue-372 percentage widths: every column is bounded
 * to its share, so a long name ellipsizes inside its own cell instead of
 * widening the table, and the 進捗 cell never leaves the slack the fixed
 * `w-1/3` column used to.
 */
function TestsTable({
  dashboard,
  onOpen,
}: {
  dashboard: HomeDashboard;
  onOpen: (route: string) => void;
}): JSX.Element {
  return (
    <table className="w-full table-fixed border-collapse text-left text-body-medium">
      <thead>
        <tr
          className="text-ui-label text-on-surface-variant"
          style={TABLE_HEAD_STYLE}
        >
          <th
            scope="col"
            className="py-sm pr-md font-normal"
            style={TABLE_COLUMN_WIDTH_STYLE.name}
          >
            テスト名
          </th>
          <th
            scope="col"
            className="py-sm pr-md font-normal"
            style={TABLE_COLUMN_WIDTH_STYLE.status}
          >
            状態
          </th>
          <th
            scope="col"
            className="py-sm pr-md text-left font-normal"
            style={TABLE_COLUMN_WIDTH_STYLE.answer}
          >
            答案数
          </th>
          <th
            scope="col"
            className="py-sm pr-md font-normal"
            style={TABLE_COLUMN_WIDTH_STYLE.progress}
          >
            進捗
          </th>
          <th
            scope="col"
            className="py-sm font-normal"
            style={TABLE_COLUMN_WIDTH_STYLE.updated}
          >
            最終更新
          </th>
          <th
            scope="col"
            className="py-sm font-normal"
            style={TABLE_COLUMN_WIDTH_STYLE.open}
          >
            <span className="sr-only">開く</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {dashboard.visibleTests.map((progress) => (
          <TestRow key={progress.test.id} progress={progress} onOpen={onOpen} />
        ))}
      </tbody>
    </table>
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
      className="border-t border-chart-axis align-middle"
    >
      <th scope="row" className="py-sm pr-md font-normal">
        <TestName progress={progress} />
      </th>
      {/* Secondary state detail lives beside the pill on the same line: the old
          block below the pill made the mock's 43px row 57px (Issue 365). */}
      <td className="py-sm pr-md">
        <div className="flex items-center gap-sm">
          <StatusPill progress={progress} />
          <BucketCounts progress={progress} />
        </div>
      </td>
      <td
        className="py-sm pr-md text-left text-on-surface"
        style={NUMERIC_STYLE}
      >
        <AnswerCount progress={progress} />
      </td>
      <td className="py-sm pr-md">
        <ProgressCell progress={progress} onOpen={onOpen} />
      </td>
      <td className="py-sm text-on-surface-variant" style={NUMERIC_STYLE}>
        {formatHomeDate(progress.lastUpdatedAt)}
      </td>
      <td className="py-sm pl-sm text-right">
        <RowChevron progress={progress} onOpen={onOpen} />
      </td>
    </tr>
  );
}

/**
 * Narrow replacement for the table: one block per test. Every column the table
 * shows stays visible — including 最終更新, which the horizontal scroller used
 * to hide — and there is no scroller, so the bright native scrollbar is gone
 * (Issue 372 §7).
 */
function TestBlockList({
  dashboard,
  onOpen,
}: {
  dashboard: HomeDashboard;
  onOpen: (route: string) => void;
}): JSX.Element {
  return (
    <ul className="flex flex-col gap-md">
      {dashboard.visibleTests.map((progress) => (
        <TestBlock key={progress.test.id} progress={progress} onOpen={onOpen} />
      ))}
    </ul>
  );
}

function TestBlock({
  progress,
  onOpen,
}: {
  progress: HomeTestProgress;
  onOpen: (route: string) => void;
}): JSX.Element {
  const test = progress.test;
  return (
    <li
      data-testid={`home-test-card-${test.id}`}
      className="flex flex-col gap-sm rounded-lg bg-surface-container-high p-md"
    >
      <div className="flex items-center justify-between gap-sm">
        <TestName progress={progress} />
        <RowChevron progress={progress} onOpen={onOpen} />
      </div>
      <div className="flex flex-wrap items-center gap-sm">
        <StatusPill progress={progress} />
        <BucketCounts progress={progress} />
      </div>
      <div className="flex min-w-0 items-center gap-sm">
        <span className="shrink-0 text-ui-label text-on-surface-variant">
          答案数
        </span>
        <span
          className="shrink-0 text-on-surface"
          style={NUMERIC_STYLE}
          data-testid={`home-test-answer-${test.id}`}
        >
          <AnswerCount progress={progress} />
        </span>
        <ProgressCell progress={progress} onOpen={onOpen} />
      </div>
      <div
        className="text-ui-label text-on-surface-variant"
        style={NUMERIC_STYLE}
      >
        <span data-testid={`home-test-updated-${test.id}`}>
          最終更新 {formatHomeDate(progress.lastUpdatedAt)}
        </span>
      </div>
    </li>
  );
}

function TestName({ progress }: { progress: HomeTestProgress }): JSX.Element {
  const test = progress.test;
  return (
    <span
      data-testid={`home-test-name-${test.id}`}
      className="block min-w-0 truncate font-normal text-on-surface"
      title={test.name}
    >
      {test.name}
    </span>
  );
}

function AnswerCount({
  progress,
}: {
  progress: HomeTestProgress;
}): JSX.Element {
  return <>{progress.answerCount ?? "—"}</>;
}

function StatusPill({ progress }: { progress: HomeTestProgress }): JSX.Element {
  const test = progress.test;
  return (
    <span
      data-testid={`home-test-status-${test.id}`}
      className={`inline-flex shrink-0 items-center rounded-full px-lg text-ui-label ${statusPillClass(progress.statusBadge)}`}
      style={STATUS_PILL_STYLE}
    >
      {progress.statusBadge.label}
    </span>
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

  const queueLabel = `確認済み ${progress.doneCount} / ${progress.total}`;

  // Issue 365: the mock's 進捗 cell holds only the track and the percent. The
  // whole area is the queue-entry button, so dropping the visible
  // "確認済み N / M" line (which squeezed the track to 56px) keeps the queue
  // reachable through the same testid and accessible name.
  //
  // Issue 372: the track is `flex-1` rather than a fixed 8.75rem. At the
  // full-width table a fixed track left its own cell's slack as the ~380px gap
  // the issue measured; filling the cell removes it.
  return (
    <div className="flex min-w-0 flex-1 items-center gap-sm whitespace-nowrap">
      <button
        type="button"
        data-testid={`home-open-queue-${test.id}`}
        onClick={() => {
          onOpen(submissionQueue(test.id));
        }}
        aria-label={queueLabel}
        className="flex min-w-0 flex-1 items-center gap-sm rounded-sm text-left text-ui-label text-primary-text hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        {summary !== null && percent !== null ? (
          <>
            {/* The track uses --color-progress-track (L+17 over the card); the
                old surface-container-high sat only L+6 away and vanished on 0%
                rows (Issue 360). */}
            <span
              role="progressbar"
              data-testid={`home-test-progress-${test.id}`}
              aria-label={`${test.name} の確認済み設問`}
              aria-valuemin={0}
              aria-valuemax={summary.total}
              aria-valuenow={summary.confirmed}
              className="block h-2 flex-1 rounded-sm bg-progress-track"
            >
              <span
                data-testid={`home-test-progress-fill-${test.id}`}
                className="block h-full rounded-sm bg-primary"
                style={{ width: `${percent}%` }}
              />
            </span>
            <span
              data-testid={`home-test-progress-percent-${test.id}`}
              className="w-9 shrink-0 text-right text-on-surface-variant"
              style={NUMERIC_STYLE}
            >
              {percent}%
            </span>
          </>
        ) : (
          <span
            data-testid={`home-test-progress-unavailable-${test.id}`}
            className="truncate text-on-surface-variant"
          >
            設問の進捗を取得できませんでした
          </span>
        )}
        <span className="sr-only">{queueLabel}</span>
      </button>
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

  // `flex-wrap` (not truncation): a status cell with several non-zero buckets
  // grows to a second line instead of hiding a count or colliding with 答案数
  // (Issue 372 §3/§7). The mock's single-bucket cells still stay on one line.
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-sm text-ui-label text-on-surface-variant">
      {shown.map(({ bucket, label, count }) => (
        <span key={bucket} className="whitespace-nowrap">
          {label} {count}件
        </span>
      ))}
    </span>
  );
}
