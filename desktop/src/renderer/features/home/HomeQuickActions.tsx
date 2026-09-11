import type { JSX, ReactNode } from "react";
import { ChevronRight, FileUp, ListChecks, Settings } from "lucide-react";

import { AppRoutes } from "../../core/app-routes.js";

function QuickAction({
  testId,
  icon,
  label,
  description,
  onOpen,
}: {
  testId: string;
  icon: ReactNode;
  label: string;
  description: string;
  onOpen: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onOpen}
      className="flex w-full items-center gap-md rounded-lg px-md py-sm text-left hover:bg-surface-container-high focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-90"
      style={{
        transitionProperty: "background-color, opacity",
        transitionDuration: "var(--motion-duration-state-change)",
        transitionTimingFunction: "var(--motion-easing-standard)",
      }}
    >
      <span
        aria-hidden
        className="flex size-9 shrink-0 items-center justify-center rounded-md bg-surface-container-high text-on-surface-variant"
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-ui-label text-on-surface">
          {label}
        </span>
        <span className="block truncate text-body-medium text-on-surface-variant">
          {description}
        </span>
      </span>
      <ChevronRight
        aria-hidden
        size={16}
        className="shrink-0 text-on-surface-variant"
      />
    </button>
  );
}

/**
 * クイックアクション (Issue #336, parent #333 §5). The three existing
 * destinations keep their data-testids; the shell's dead search field is
 * deliberately not reproduced (parent #333 §4).
 */
export function HomeQuickActions({
  onOpen,
}: {
  onOpen: (route: string) => void;
}): JSX.Element {
  return (
    <section
      data-testid="home-quick-actions"
      className="rounded-xl bg-surface-container p-lg"
    >
      <h2 className="text-body-medium font-semibold text-on-surface">
        クイックアクション
      </h2>
      <div className="mt-md flex flex-col gap-xs">
        <QuickAction
          testId="home-open-intake"
          icon={<FileUp size={18} />}
          label="資料を取り込む"
          description="採点基準と答案をまとめて取り込む"
          onOpen={() => {
            onOpen(AppRoutes.intake);
          }}
        />
        <QuickAction
          testId="home-open-test-list-footer"
          icon={<ListChecks size={18} />}
          label="テスト一覧"
          description="登録したテストと進み具合を見る"
          onOpen={() => {
            onOpen(AppRoutes.testList);
          }}
        />
        <QuickAction
          testId="home-open-settings"
          icon={<Settings size={18} />}
          label="設定"
          description="AI の接続と資料の型を整える"
          onOpen={() => {
            onOpen(AppRoutes.settings);
          }}
        />
      </div>
    </section>
  );
}
