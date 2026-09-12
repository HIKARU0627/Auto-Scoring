import {
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
  type JSX,
} from "react";

import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
  AppRoutes,
  submissionQueue,
  testSettings,
} from "../../core/app-routes.js";
import {
  HomeDashboard,
  type HomeTestProgress,
} from "../../core/home-dashboard.js";
import { HomeDataError, loadHomeDashboard } from "../../core/home-data.js";
import { formatHomeDate } from "../../core/home-analytics.js";
import { AppErrorBanner } from "../../core/AppErrorBanner.js";
import { ShellScreen } from "../../navigation/ShellScreen.js";
import { useRouter } from "../../navigation/router.js";
import {
  NUMERIC_STYLE,
  PANEL_TITLE_STYLE,
  STATUS_PILL_STYLE,
  statusPillClass,
  TABLE_HEAD_STYLE,
} from "../home/home-format.js";
import { ScreenSkeleton, secondaryButtonClass } from "../ui/screen-ui.js";

/**
 * The full test list (Issue #379). Every registered test -- `draft` and `ready`
 * alike -- with the same row content as the home dashboard's recent-tests table
 * (`HomeRecentTestsTable`), plus an explicit entry to each test's settings and
 * answer queue.
 *
 * The data source is the existing `GET /test-registrations` (draft included),
 * aggregated through `HomeDashboard` so the status pill, answer count, progress,
 * and last-updated columns are the same numbers the home screen shows instead of
 * a second definition. No backend endpoint was added.
 *
 * Home's components are deliberately not reused or refactored (Issue #379
 * plan): only the pure presentation helpers in `home-format.ts` are shared so
 * the pill's colour mapping cannot drift between the two screens.
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

/** Issue #372 column split, extended with the actions column of this screen. */
const COLUMN_WIDTH_STYLE: {
  readonly name: CSSProperties;
  readonly status: CSSProperties;
  readonly answer: CSSProperties;
  readonly progress: CSSProperties;
  readonly updated: CSSProperties;
  readonly actions: CSSProperties;
} = {
  name: { width: "25%" },
  status: { width: "15%" },
  answer: { width: "9%" },
  progress: { width: "18%" },
  updated: { width: "14%" },
  actions: { width: "19%" },
};

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; dashboard: HomeDashboard };

function errorText(error: unknown): string {
  if (error instanceof HomeDataError) {
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
}

export function TestListPage(): JSX.Element {
  const client = useSidecarClient();
  const { push } = useRouter();
  const narrow = useNarrowLayout();
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });

  const reload = useCallback(async () => {
    setLoadState({ status: "loading" });
    try {
      const dashboard = await loadHomeDashboard(client);
      setLoadState({ status: "ready", dashboard });
    } catch (error) {
      setLoadState({ status: "error", message: errorText(error) });
    }
  }, [client]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const open = useCallback(
    (route: string) => {
      push(route);
    },
    [push],
  );

  return (
    <ShellScreen title="テスト一覧">
      {loadState.status === "loading" ? (
        <ScreenSkeleton testId="test-list-loading" />
      ) : null}

      {loadState.status === "error" ? (
        <AppErrorBanner
          testId="test-list-error"
          message={`テスト一覧を取得できません: ${loadState.message}`}
          onRetry={() => {
            void reload();
          }}
        />
      ) : null}

      {loadState.status === "ready" ? (
        loadState.dashboard.isEmpty ? (
          <EmptyTestList
            onOpenIntake={() => {
              open(AppRoutes.intake);
            }}
          />
        ) : (
          <div
            data-testid="test-list-table"
            className="min-w-0 rounded-xl bg-surface-container p-xl"
          >
            <h2
              className="font-semibold text-heading"
              style={PANEL_TITLE_STYLE}
            >
              登録済みのテスト
            </h2>
            <p className="mt-xs text-body-medium text-on-surface-variant">
              {loadState.dashboard.tests.length}件
            </p>
            <div className="mt-md">
              {narrow ? (
                <TestBlockList dashboard={loadState.dashboard} onOpen={open} />
              ) : (
                <TestsTable dashboard={loadState.dashboard} onOpen={open} />
              )}
            </div>
          </div>
        )
      ) : null}
    </ShellScreen>
  );
}

function EmptyTestList({
  onOpenIntake,
}: {
  onOpenIntake: () => void;
}): JSX.Element {
  return (
    <div
      data-testid="test-list-empty"
      className="rounded-xl bg-surface-container p-xl"
    >
      <h2 className="font-semibold text-heading" style={PANEL_TITLE_STYLE}>
        まだテストがありません
      </h2>
      <p className="mt-sm text-body-medium text-on-surface-variant">
        資料の取込から、答案と採点基準を取り込むとここに並びます。取り込んだあと、配点と回答欄を確認すると採点を始められます。
      </p>
      <button
        type="button"
        data-testid="test-list-empty-intake"
        onClick={onOpenIntake}
        className={`mt-lg ${secondaryButtonClass()}`}
      >
        資料の取込を開く
      </button>
    </div>
  );
}

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
            style={COLUMN_WIDTH_STYLE.name}
          >
            テスト名
          </th>
          <th
            scope="col"
            className="py-sm pr-md font-normal"
            style={COLUMN_WIDTH_STYLE.status}
          >
            状態
          </th>
          <th
            scope="col"
            className="py-sm pr-md text-left font-normal"
            style={COLUMN_WIDTH_STYLE.answer}
          >
            答案数
          </th>
          <th
            scope="col"
            className="py-sm pr-md font-normal"
            style={COLUMN_WIDTH_STYLE.progress}
          >
            進捗
          </th>
          <th
            scope="col"
            className="py-sm pr-md font-normal"
            style={COLUMN_WIDTH_STYLE.updated}
          >
            最終更新
          </th>
          <th
            scope="col"
            className="py-sm font-normal"
            style={COLUMN_WIDTH_STYLE.actions}
          >
            操作
          </th>
        </tr>
      </thead>
      <tbody>
        {dashboard.tests.map((progress) => (
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
      data-testid={`test-list-row-${test.id}`}
      className="border-t border-chart-axis align-middle"
    >
      <th scope="row" className="py-md pr-md font-normal">
        <span
          data-testid={`test-list-name-${test.id}`}
          className="block min-w-0 truncate text-on-surface"
          title={test.name}
        >
          {test.name}
        </span>
      </th>
      <td className="py-md pr-md">
        <StatusPill progress={progress} />
      </td>
      <td
        className="py-md pr-md text-left text-on-surface"
        style={NUMERIC_STYLE}
      >
        {progress.answerCount ?? "—"}
      </td>
      <td className="py-md pr-md">
        <ProgressCell progress={progress} />
      </td>
      <td className="py-md pr-md text-on-surface-variant" style={NUMERIC_STYLE}>
        {formatHomeDate(progress.lastUpdatedAt)}
      </td>
      <td className="py-md">
        <RowActions testId={test.id} onOpen={onOpen} />
      </td>
    </tr>
  );
}

function TestBlockList({
  dashboard,
  onOpen,
}: {
  dashboard: HomeDashboard;
  onOpen: (route: string) => void;
}): JSX.Element {
  return (
    <ul className="flex flex-col gap-md">
      {dashboard.tests.map((progress) => (
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
      data-testid={`test-list-row-${test.id}`}
      className="flex flex-col gap-sm rounded-lg bg-surface-container-high p-md"
    >
      <div className="flex items-center justify-between gap-sm">
        <span
          data-testid={`test-list-name-${test.id}`}
          className="block min-w-0 truncate text-on-surface"
          title={test.name}
        >
          {test.name}
        </span>
        <StatusPill progress={progress} />
      </div>
      <div className="flex min-w-0 items-center gap-sm">
        <span className="shrink-0 text-ui-label text-on-surface-variant">
          答案数
        </span>
        <span className="shrink-0 text-on-surface" style={NUMERIC_STYLE}>
          {progress.answerCount ?? "—"}
        </span>
        <ProgressCell progress={progress} />
      </div>
      <div
        className="text-ui-label text-on-surface-variant"
        style={NUMERIC_STYLE}
      >
        最終更新 {formatHomeDate(progress.lastUpdatedAt)}
      </div>
      <RowActions testId={test.id} onOpen={onOpen} />
    </li>
  );
}

function StatusPill({ progress }: { progress: HomeTestProgress }): JSX.Element {
  const test = progress.test;
  return (
    <span
      data-testid={`test-list-status-${test.id}`}
      className={`inline-flex shrink-0 items-center rounded-full px-lg text-ui-label ${statusPillClass(progress.statusBadge)}`}
      style={STATUS_PILL_STYLE}
    >
      {progress.statusBadge.label}
    </span>
  );
}

function ProgressCell({
  progress,
}: {
  progress: HomeTestProgress;
}): JSX.Element {
  const test = progress.test;
  if (progress.answerCount === null) {
    return (
      <span
        data-testid={`test-list-progress-unavailable-${test.id}`}
        className="text-ui-label text-on-surface-variant"
      >
        答案を取得できませんでした
      </span>
    );
  }

  const summary = progress.reviewSummary;
  const percent = progress.reviewPercent;
  if (summary === null || percent === null) {
    return (
      <span
        data-testid={`test-list-progress-unavailable-${test.id}`}
        className="text-ui-label text-on-surface-variant"
      >
        —
      </span>
    );
  }

  return (
    <div className="flex min-w-0 items-center gap-sm whitespace-nowrap">
      <span
        role="progressbar"
        data-testid={`test-list-progress-${test.id}`}
        aria-label={`${test.name} の確認済み設問`}
        aria-valuemin={0}
        aria-valuemax={summary.total}
        aria-valuenow={summary.confirmed}
        className="block h-2 min-w-0 flex-1 rounded-sm bg-progress-track"
      >
        <span
          className="block h-full rounded-sm bg-primary"
          style={{ width: `${percent}%` }}
        />
      </span>
      <span
        data-testid={`test-list-progress-percent-${test.id}`}
        className="w-9 shrink-0 text-right text-on-surface-variant"
        style={NUMERIC_STYLE}
      >
        {percent}%
      </span>
    </div>
  );
}

function RowActions({
  testId,
  onOpen,
}: {
  testId: string;
  onOpen: (route: string) => void;
}): JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-sm">
      <button
        type="button"
        data-testid={`test-list-open-settings-${testId}`}
        onClick={() => {
          onOpen(testSettings(testId));
        }}
        className={secondaryButtonClass()}
      >
        テスト設定
      </button>
      <button
        type="button"
        data-testid={`test-list-open-queue-${testId}`}
        onClick={() => {
          onOpen(submissionQueue(testId));
        }}
        className={secondaryButtonClass()}
      >
        答案キュー
      </button>
    </div>
  );
}
