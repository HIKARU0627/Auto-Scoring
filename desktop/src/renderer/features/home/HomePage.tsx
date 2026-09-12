import {
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
  type JSX,
} from "react";
import { RefreshCw } from "lucide-react";

import { whileRunningRequirements } from "../../core/action-requirements.js";
import {
  HomeDashboard,
  type HomeNextAction,
} from "../../core/home-dashboard.js";
import { HomeDataError, loadHomeDashboard } from "../../core/home-data.js";
import { AppErrorBanner } from "../../core/AppErrorBanner.js";
import {
  formatRefreshClockTime,
  useRefreshState,
} from "../../core/use-refresh-state.js";
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
  | { status: "ready"; dashboard: HomeDashboard };

/**
 * The mock measures the main-column card pitch at 21/22px, while the space
 * scale's `xl` step is 24px (Issue #367, parent #333). `features/` may not add
 * a raw numeric spacing utility (`design-tokens-lint.test.ts`), so the measured
 * literal lives here next to the components that carry it.
 */
const MAIN_COLUMN_GAP_STYLE: CSSProperties = { gap: "21px" };

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
 * is not copied.
 *
 * Issue 375 items 7-8: the page heading is the top of the type hierarchy, so it
 * takes `--color-heading` (the mock's #FFFFFF, like the card headings) and a
 * measured ~1.5x of the card heading. 32px * 1.5 = 48px lands on the mock's
 * 43px glyph height. The size is an inline style because `features/` may not
 * add a `text-headline-*` utility; see the PR body.
 */
export function HomePage(): JSX.Element {
  const client = useSidecarClient();
  const { pathname, push } = useRouter();
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  // Issue #383: the reload button's loading feedback and the last-updated
  // label come from the shared hook, so every screen that adopts it behaves
  // the same and tests drive the clock with fake timers.
  const { showLoading, lastUpdatedAt, run } = useRefreshState({
    now: () => new Date(),
  });

  const reload = useCallback(async () => {
    setLoadState((previous) =>
      previous.status === "ready" ? previous : { status: "loading" },
    );
    try {
      const dashboard = await run(() => loadHomeDashboard(client));
      setLoadState({ status: "ready", dashboard });
    } catch (error) {
      setLoadState({ status: "error", message: errorText(error) });
    }
  }, [client, run]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const open = useCallback(
    (route: string) => {
      push(route);
    },
    [push],
  );

  // The skeleton owns the first load; `showLoading` owns the reload, and is
  // already delayed and held by the hook, so a fast reload shows no busy reason.
  const running = loadState.status === "loading" || showLoading;
  const busyReasons = whileRunningRequirements({ running });

  return (
    <div
      data-testid="home-page"
      className="flex min-w-0 flex-col text-on-surface"
    >
      <header className="flex items-start justify-between gap-md px-sm pt-lg pb-md">
        <div className="min-w-0 flex-1">
          <h1
            data-testid="page-title"
            className="font-medium leading-ui text-heading"
            style={{
              fontSize: "calc(var(--font-size-headline-large) * 1.5)",
            }}
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
            className="inline-flex items-center gap-sm rounded-md bg-surface-container-high px-md py-xs text-ui-label text-on-surface hover:bg-surface-container-highest focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-90 disabled:opacity-50"
          >
            <RefreshCw aria-hidden size={15} />
            最新の状況に更新
          </button>
          {/* Issue 383: always-visible proof that a reload happened. The value
              changes on every successful reload, and stays put on a failure so
              the error banner is the only thing that moves. */}
          <p
            data-testid="home-last-updated"
            className="mt-xs text-ui-label text-on-surface-variant"
          >
            最終更新 {formatRefreshClockTime(lastUpdatedAt)}
          </p>
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

      {/* `relative overflow-x-clip` (Issue 367): the recent-tests table's
          scroll container is not a positioned ancestor, so the absolutely
          positioned `.sr-only` in its last column was laid out against the
          viewport and widened the document to x≈760 at 700px. Making this
          content region a positioned clip box contains that visually hidden
          node without touching the table (Issue 365's territory).
          Issue 375 item 4: the bottom `pb-xl` is gone too; the shell frame's
          own `p-xl` already insets the panel, and the doubled 24px left a band
          of bare surface under 最近のテスト in a window taller than the
          content. */}
      <main className="relative min-w-0 flex-1 overflow-x-clip px-sm">
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
    <div className="flex flex-col" style={MAIN_COLUMN_GAP_STYLE}>
      {dashboard.degradedTests.length > 0 ? (
        <DegradedNotice dashboard={dashboard} />
      ) : null}
      {/* Issue 375 (F6): the quick actions move back beside the hero -- the
          position the mock gives the top of its right rail. Folding them into
          the body flow (Issue 372) removed the empty rail but added a full-width
          block above the table, and at 1536x1024 pushed 最近のテスト's only data
          row below the fold. The hero and the quick actions share one grid row,
          the two graph cards share the next, and the table spans the full width
          below both. Every row fills the width, so a rail-shaped bare-surface
          hole cannot reappear. The mock's お知らせ / 最近の作業 cards are not
          reproduced: this product has no source for them (parent Issue 333 §4). */}
      <div className="flex min-w-0 flex-col" style={MAIN_COLUMN_GAP_STYLE}>
        <div className="grid min-w-0 items-stretch gap-xl lg:grid-cols-3">
          <div className="min-w-0 lg:col-span-2">
            <HomeHeroCard
              action={dashboard.nextAction}
              onAction={() => {
                handleAction(dashboard.nextAction);
              }}
            />
          </div>
          {/* Issue 375 item 3: the row layout belongs to HomeQuickActions now.
              The old `[&>section>div]:grid` parent/descendant selector reached
              into its DOM; moving the card must not depend on that. */}
          <div className="min-w-0">
            <HomeQuickActions onOpen={onOpen} />
          </div>
        </div>
        {/* Issue 360: the mock splits the main column into 全体の進捗 (wider)
            and テストの進捗 (narrower) side by side, instead of stacking the
            donut under the quick-action rail. Issue 375 item 12: an even split
            narrows 全体の進捗 enough that its four KPI columns land near the
            mock's 128px pitch. */}
        <div className="grid min-w-0 items-stretch gap-xl lg:grid-cols-2">
          <div className="min-w-0">
            <HomeProgressPanel dashboard={dashboard} />
          </div>
          <div className="min-w-0">
            <HomeTestDonutPanel dashboard={dashboard} />
          </div>
        </div>
      </div>
      <HomeRecentTestsTable dashboard={dashboard} onOpen={onOpen} />
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
