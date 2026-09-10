import { useCallback, useEffect, useState, type JSX } from "react";

import {
  AppRoutes,
  pdfReview,
  submissionQueue,
  testSettings,
} from "../../core/app-routes.js";
import {
  HomeDashboard,
  type HomeNextAction,
  type HomeTestProgress,
} from "../../core/home-dashboard.js";
import {
  HomeWorkBucket,
  homeWorkBucketMeta,
} from "../../core/submission-work-bucket.js";
import { HomeDataError, loadHomeDashboard } from "../../api/home-data.js";
import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import { useRouter } from "../../navigation/router.js";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; dashboard: HomeDashboard };

function toneClass(tone: HomeNextAction["tone"]): string {
  switch (tone) {
    case "attention":
      return "text-attention";
    case "danger":
      return "text-error";
    case "success":
      return "text-success";
    default:
      return "text-on-surface-variant";
  }
}

export function HomePage(): JSX.Element {
  const client = useSidecarClient();
  const { push } = useRouter();
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });

  const reload = useCallback(async () => {
    setLoadState({ status: "loading" });
    try {
      const dashboard = await loadHomeDashboard(client);
      setLoadState({ status: "ready", dashboard });
    } catch (error) {
      const message =
        error instanceof HomeDataError
          ? error.message
          : error instanceof Error
            ? error.message
            : String(error);
      setLoadState({ status: "error", message });
    }
  }, [client]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const openAndReload = useCallback(
    async (route: string) => {
      push(route);
      await reload();
    },
    [push, reload],
  );

  return (
    <div className="min-h-screen bg-surface text-on-surface">
      <header className="flex items-center justify-between border-b border-outline-variant px-xl py-md">
        <h1 className="text-title-large font-medium leading-ui">
          Auto-Scoring
        </h1>
        <button
          type="button"
          data-testid="home-refresh"
          className="rounded-md border border-outline px-md py-xs text-ui-label"
          onClick={() => {
            void reload();
          }}
        >
          最新の状況に更新
        </button>
      </header>

      <main className="mx-auto max-w-[960px] p-xl">
        {loadState.status === "loading" ? (
          <p className="text-body-medium text-on-surface-variant">
            読み込み中…
          </p>
        ) : null}

        {loadState.status === "error" ? (
          <div
            data-testid="home-error"
            className="rounded-md border border-error bg-error-container p-lg text-on-error-container"
          >
            <p className="text-body-medium">
              作業状況を取得できません: {loadState.message}
            </p>
            <button
              type="button"
              className="mt-md rounded-md border border-outline px-md py-xs text-ui-label"
              onClick={() => {
                void reload();
              }}
            >
              再試行
            </button>
          </div>
        ) : null}

        {loadState.status === "ready" ? (
          <DashboardBody
            dashboard={loadState.dashboard}
            onOpen={(route) => {
              void openAndReload(route);
            }}
            onRefresh={() => {
              void reload();
            }}
          />
        ) : null}

        <div className="mt-xl border-t border-outline-variant pt-md">
          <EntryPointRow
            onOpen={(route) => {
              void openAndReload(route);
            }}
          />
        </div>
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
  const action = dashboard.nextAction;
  return (
    <div className="flex flex-col gap-xl">
      <NextUpCard action={action} onOpen={onOpen} onRefresh={onRefresh} />
      {dashboard.visibleTests.length > 0 ? (
        <section>
          <SectionHeader
            hiddenTestCount={dashboard.hiddenTestCount}
            onOpen={onOpen}
          />
          <div className="mt-sm flex flex-col gap-md">
            {dashboard.visibleTests.map((progress) => (
              <TestProgressCard
                key={progress.test.id}
                progress={progress}
                onOpen={onOpen}
              />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function NextUpCard({
  action,
  onOpen,
  onRefresh,
}: {
  action: HomeNextAction;
  onOpen: (route: string) => void;
  onRefresh: () => void;
}): JSX.Element {
  const route = action.route;
  return (
    <section
      data-testid="home-next-up"
      className="rounded-lg border border-outline-variant bg-surface-container-low p-lg"
    >
      <div className="flex gap-lg">
        <div
          className={`text-title-large ${toneClass(action.tone)}`}
          aria-hidden
        >
          ●
        </div>
        <div className="flex-1">
          <h2 className="text-title-large font-medium leading-ui">
            {action.headline}
          </h2>
          <p className="mt-xs text-body-medium text-on-surface-variant">
            {action.detail}
          </p>
        </div>
      </div>
      <div className="mt-lg flex justify-end">
        <button
          type="button"
          data-testid="home-next-up-action"
          className="rounded-md bg-primary px-lg py-sm text-ui-label text-on-primary"
          onClick={() => {
            if (route === null) {
              onRefresh();
              return;
            }
            onOpen(route);
          }}
        >
          {action.actionLabel}
        </button>
      </div>
    </section>
  );
}

function SectionHeader({
  hiddenTestCount,
  onOpen,
}: {
  hiddenTestCount: number;
  onOpen: (route: string) => void;
}): JSX.Element {
  return (
    <div className="flex items-center justify-between">
      <h2 className="text-title-medium font-medium">テストの進み具合</h2>
      {hiddenTestCount > 0 ? (
        <button
          type="button"
          data-testid="home-open-hidden-tests"
          className="text-ui-label text-primary"
          onClick={() => {
            onOpen(AppRoutes.testList);
          }}
        >
          他{hiddenTestCount}件を見る
        </button>
      ) : null}
    </div>
  );
}

function TestProgressCard({
  progress,
  onOpen,
}: {
  progress: HomeTestProgress;
  onOpen: (route: string) => void;
}): JSX.Element {
  const test = progress.test;
  const resume = resumeAction(progress, onOpen);
  return (
    <article
      data-testid={`home-test-card-${test.id}`}
      className="rounded-lg border border-outline-variant bg-surface-container-low p-lg"
    >
      <h3 className="text-title-medium font-medium">{test.name}</h3>
      {progress.isDraft ? (
        <p className="mt-sm text-body-medium text-on-surface-variant">
          登録が未完了です。回答欄と設問依存関係を確認するまで答案を取り込めません。
        </p>
      ) : (
        <>
          <SubmissionProgress progress={progress} onOpen={onOpen} />
          <BucketCounts progress={progress} />
        </>
      )}
      {resume}
    </article>
  );
}

function SubmissionProgress({
  progress,
  onOpen,
}: {
  progress: HomeTestProgress;
  onOpen: (route: string) => void;
}): JSX.Element | null {
  if (progress.total === 0) {
    return (
      <p className="mt-sm text-body-medium text-on-surface-variant">
        まだ答案が取り込まれていません
      </p>
    );
  }

  const done = progress.doneCount;
  const total = progress.total;
  return (
    <button
      type="button"
      data-testid={`home-open-queue-${progress.test.id}`}
      className="mt-sm w-full rounded-md px-xs py-xs text-left"
      onClick={() => {
        onOpen(submissionQueue(progress.test.id));
      }}
    >
      <div className="flex items-center gap-xs text-body-medium">
        <span>
          確認済み {done} / {total}
        </span>
        <span aria-hidden>›</span>
      </div>
      <div
        className="mt-xs h-2 rounded-sm bg-surface-container-high"
        role="progressbar"
        aria-label={`${progress.test.name} の確認済み答案`}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
      >
        <div
          className="h-full rounded-sm bg-primary"
          style={{ width: `${(done / total) * 100}%` }}
        />
      </div>
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
    <div className="mt-sm flex flex-wrap gap-md text-ui-label">
      {shown.map(({ label, count }) => (
        <span key={label}>
          {label} {count}件
        </span>
      ))}
    </div>
  );
}

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
        className="mt-md rounded-md bg-secondary-container px-md py-sm text-ui-label text-on-secondary-container"
        onClick={() => {
          onOpen(testSettings(test.id));
        }}
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
      className="mt-md rounded-md bg-secondary-container px-md py-sm text-ui-label text-on-secondary-container"
      onClick={() => {
        onOpen(pdfReview(test.id, resumable.id));
      }}
    >
      {label}
    </button>
  );
}

function EntryPointRow({
  onOpen,
}: {
  onOpen: (route: string) => void;
}): JSX.Element {
  return (
    <div className="flex flex-wrap gap-sm">
      <button
        type="button"
        data-testid="home-open-intake"
        className="rounded-md border border-outline px-md py-sm text-ui-label"
        onClick={() => {
          onOpen(AppRoutes.intake);
        }}
      >
        資料を取り込む
      </button>
      <button
        type="button"
        data-testid="home-open-test-list-footer"
        className="rounded-md border border-outline px-md py-sm text-ui-label"
        onClick={() => {
          onOpen(AppRoutes.testList);
        }}
      >
        テスト一覧
      </button>
      <button
        type="button"
        data-testid="home-open-settings"
        className="rounded-md border border-outline px-md py-sm text-ui-label"
        onClick={() => {
          onOpen(AppRoutes.settings);
        }}
      >
        設定
      </button>
    </div>
  );
}

const HOME_WORK_BUCKET_ORDER = [
  HomeWorkBucket.needsReview,
  HomeWorkBucket.intakeDone,
  HomeWorkBucket.processing,
  HomeWorkBucket.failed,
  HomeWorkBucket.done,
] as const;
