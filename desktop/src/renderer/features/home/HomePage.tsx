import { useCallback, useEffect, useState, type JSX } from "react";
import { RefreshCw } from "lucide-react";

import { whileRunningRequirements } from "../../core/action-requirements.js";
import {
  HomeDashboard,
  type HomeNextAction,
} from "../../core/home-dashboard.js";
import { HomeDataError, loadHomeDashboard } from "../../core/home-data.js";
import { AppErrorBanner } from "../../core/AppErrorBanner.js";
import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import { pageSubtitleFor } from "../../navigation/page-header.js";
import { useRouter } from "../../navigation/router.js";
import { HomeDashboardSkeleton } from "./HomeDashboardSkeleton.js";
import { HomeHeroCard } from "./HomeHeroCard.js";
import { HomeProgressPanel } from "./HomeProgressPanel.js";
import { HomeQuickActions } from "./HomeQuickActions.js";
import { HomeRecentTestsTable } from "./HomeRecentTestsTable.js";
import { HomeTestDonutPanel } from "./HomeTestDonutPanel.js";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; dashboard: HomeDashboard; refreshing: boolean };

function errorText(error: unknown): string {
  if (error instanceof HomeDataError) {
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
}

/**
 * The home dashboard (Issue #336). The sidebar and the content column come
 * from the shell (#335); this feature renders the dashboard body, its
 * loading/empty/error/partial states, and the quick-action entry points whose
 * data-testids the E2E probes depend on.
 *
 * Home repeats the shell's page heading treatment here instead of calling
 * `ShellScreen`: `ShellScreen` always renders the escape control, and home must
 * not show one (INV-018). The subtitle still comes from `page-header.ts` so it
 * is not copied. The heading's size comes from `--font-size-headline-large`
 * (the mock's page title is ~14% larger than the shared headline-medium) through
 * an inline style because the token layer has no `text-headline-*` utility and
 * `features/` may not add one; see the PR body.
 */
export function HomePage(): JSX.Element {
  const client = useSidecarClient();
  const { pathname, push } = useRouter();
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });

  const reload = useCallback(async () => {
    setLoadState((previous) =>
      previous.status === "ready"
        ? { status: "ready", dashboard: previous.dashboard, refreshing: true }
        : { status: "loading" },
    );
    try {
      const dashboard = await loadHomeDashboard(client);
      setLoadState({ status: "ready", dashboard, refreshing: false });
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

  const running =
    loadState.status === "loading" ||
    (loadState.status === "ready" && loadState.refreshing);
  const busyReasons = whileRunningRequirements({ running });

  return (
    <div
      data-testid="home-page"
      className="flex min-h-full min-w-0 flex-col text-on-surface"
    >
      <header className="flex items-start justify-between gap-md px-xl pt-lg pb-md">
        <div className="min-w-0 flex-1">
          <h1
            data-testid="page-title"
            className="font-medium leading-ui text-on-surface"
            style={{ fontSize: "var(--font-size-headline-large)" }}
          >
            ホーム
          </h1>
          <p className="mt-xs text-body-medium text-on-surface-variant">
            {pageSubtitleFor(pathname)}
          </p>
        </div>
        <div className="flex flex-col items-end">
          <button
            type="button"
            data-testid="home-refresh"
            disabled={running}
            onClick={() => {
              void reload();
            }}
            className="inline-flex items-center gap-sm rounded-md border border-outline px-md py-xs text-ui-label text-on-surface hover:bg-surface-container focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-90 disabled:opacity-50"
          >
            <RefreshCw aria-hidden size={15} />
            最新の状況に更新
          </button>
          {busyReasons.map((reason) => (
            <p
              key={reason.id}
              data-testid={`home-reason-${reason.id}`}
              className="mt-xs text-ui-label text-on-surface-variant"
            >
              {reason.message}
            </p>
          ))}
        </div>
      </header>

      <main className="min-w-0 flex-1 px-xl pb-xl">
        {loadState.status === "loading" ? (
          <div className="flex flex-col gap-lg">
            <HomeDashboardSkeleton />
            <HomeQuickActions onOpen={open} />
          </div>
        ) : null}

        {loadState.status === "error" ? (
          <div className="flex flex-col gap-lg">
            <AppErrorBanner
              testId="home-error"
              message={`作業状況を取得できません: ${loadState.message}`}
              onRetry={() => {
                void reload();
              }}
            />
            <HomeQuickActions onOpen={open} />
          </div>
        ) : null}

        {loadState.status === "ready" ? (
          loadState.dashboard.isEmpty ? (
            <EmptyHome
              action={loadState.dashboard.nextAction}
              onAction={() => {
                const route = loadState.dashboard.nextAction.route;
                if (route === null) {
                  void reload();
                  return;
                }
                open(route);
              }}
              onOpen={open}
            />
          ) : (
            <DashboardBody
              dashboard={loadState.dashboard}
              onOpen={open}
              onRefresh={() => {
                void reload();
              }}
            />
          )
        ) : null}
      </main>
    </div>
  );
}

function DashboardBody({
  dashboard,
  onOpen,
  onRefresh,
}: {
  dashboard: HomeDashboard;
  onOpen: (route: string) => void;
  onRefresh: () => void;
}): JSX.Element {
  const handleAction = useCallback(
    (action: HomeNextAction) => {
      if (action.route === null) {
        onRefresh();
        return;
      }
      onOpen(action.route);
    },
    [onOpen, onRefresh],
  );

  return (
    <div className="flex flex-col gap-xl">
      {dashboard.degradedTests.length > 0 ? (
        <DegradedNotice dashboard={dashboard} />
      ) : null}
      {/* Two independent stacks rather than one auto-placed grid: with a grid,
          the taller right rail stretched the hero's row and left 143px of dead
          page colour under it (Issue 353, evaluation A). The mock keeps the
          table in the main column, so the table stays here too. */}
      <div className="flex flex-col gap-xl lg:flex-row lg:items-start">
        <div className="flex min-w-0 flex-1 flex-col gap-xl">
          <HomeHeroCard
            action={dashboard.nextAction}
            onAction={() => {
              handleAction(dashboard.nextAction);
            }}
          />
          <HomeProgressPanel dashboard={dashboard} />
          <HomeRecentTestsTable dashboard={dashboard} onOpen={onOpen} />
        </div>
        <div className="flex min-w-0 flex-col gap-xl lg:w-1/3">
          <HomeQuickActions onOpen={onOpen} />
          <HomeTestDonutPanel dashboard={dashboard} />
        </div>
      </div>
    </div>
  );
}

function DegradedNotice({
  dashboard,
}: {
  dashboard: HomeDashboard;
}): JSX.Element {
  const names = dashboard.degradedTests.map((test) => test.testName).join("、");
  return (
    <div
      role="status"
      data-testid="home-degraded"
      className="rounded-xl border border-outline-variant bg-surface-container p-lg text-body-medium text-on-surface-variant"
    >
      <p>
        一部のテストの答案を取得できませんでした（{names}）。そのテストの件数は
        下の集計に含めていません。「最新の状況に更新」でもう一度試せます。
      </p>
    </div>
  );
}

function EmptyHome({
  action,
  onAction,
  onOpen,
}: {
  action: HomeNextAction;
  onAction: () => void;
  onOpen: (route: string) => void;
}): JSX.Element {
  return (
    <div data-testid="home-empty-state" className="flex flex-col gap-lg">
      <HomeHeroCard action={action} onAction={onAction} />
      <div className="rounded-xl bg-surface-container p-lg">
        <h2 className="text-body-medium font-semibold text-on-surface">
          ダッシュボードに何が並ぶか
        </h2>
        <ul className="mt-sm flex flex-col gap-xs text-body-medium text-on-surface-variant">
          <li>・取り込んだ答案が日ごとに何件届いたか（直近7日）</li>
          <li>・テストが準備中・進行中・完了のどれだけあるか</li>
          <li>・テストごとの答案数と確認済みの進み具合</li>
        </ul>
        <p className="mt-sm text-body-medium text-on-surface-variant">
          資料を取り込むと、ここに実データが並びます。
        </p>
      </div>
      <HomeQuickActions onOpen={onOpen} />
    </div>
  );
}
