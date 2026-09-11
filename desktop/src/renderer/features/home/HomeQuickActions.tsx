import type { JSX, ReactNode } from "react";
import { ChevronRight, FileUp, ListChecks, Settings } from "lucide-react";

import { AppRoutes } from "../../core/app-routes.js";
import {
  PANEL_TITLE_STYLE,
  QUICK_ACTION_SUBTITLE_STYLE,
} from "./home-format.js";

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
      className="flex w-full items-center gap-sm rounded-lg bg-surface-container-highest px-md py-md text-left hover:bg-surface-bright focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-90"
      style={{
        transitionProperty: "background-color, opacity",
        transitionDuration: "var(--motion-duration-state-change)",
        transitionTimingFunction: "var(--motion-easing-standard)",
      }}
    >
      {/* Issue 360: fixed 28px icon column with an 8px gap. The old 36px box
          around an 18px glyph left a 23px dead band between icon and text. */}
      <span
        aria-hidden
        className="flex w-6 shrink-0 items-center justify-center text-on-surface"
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-ui-label text-on-surface">
          {label}
        </span>
        <span
          className="block truncate text-on-surface-variant"
          style={QUICK_ACTION_SUBTITLE_STYLE}
        >
          {description}
        </span>
      </span>
      <ChevronRight
        aria-hidden
        size={14}
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
      className="rounded-xl bg-surface-container p-xl"
    >
      <h2 className="font-semibold text-on-surface" style={PANEL_TITLE_STYLE}>
        クイックアクション
      </h2>
      {/* Each row is its own raised surface (page → card → row), so it reads
          as a pressable item rather than a line of text (Issue 353). */}
      <div className="mt-md flex flex-col gap-sm">
        <QuickAction
          testId="home-open-intake"
          icon={<FileUp size={24} fill="currentColor" />}
          label="資料を取り込む"
          description="採点基準と答案をまとめて取り込む"
          onOpen={() => {
            onOpen(AppRoutes.intake);
          }}
        />
        <QuickAction
          testId="home-open-test-list-footer"
          icon={<ListChecks size={24} fill="currentColor" />}
          label="テスト一覧"
          description="登録したテストと進み具合を見る"
          onOpen={() => {
            onOpen(AppRoutes.testList);
          }}
        />
        <QuickAction
          testId="home-open-settings"
          icon={<Settings size={24} fill="currentColor" />}
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
