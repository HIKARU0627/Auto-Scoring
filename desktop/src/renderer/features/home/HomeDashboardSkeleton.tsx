import type { JSX } from "react";

function Bar({ className }: { className: string }): JSX.Element {
  return (
    <span
      className={`block animate-pulse rounded-md bg-surface-container-high ${className}`}
    />
  );
}

/**
 * Loading placeholder for the dashboard (Issue #336). It repeats the real
 * grid's columns and heights so the page does not jump when data arrives --
 * the owner's completion rule calls a height change after load a failure.
 */
export function HomeDashboardSkeleton(): JSX.Element {
  return (
    <div
      data-testid="home-loading"
      aria-busy="true"
      aria-live="polite"
      className="flex flex-col gap-lg"
    >
      <span className="sr-only">作業状況を読み込んでいます…</span>
      <div className="rounded-xl bg-surface-container p-lg">
        <div className="flex items-center gap-lg">
          <Bar className="size-14 shrink-0 rounded-lg" />
          <div className="flex flex-1 flex-col gap-sm">
            <Bar className="h-4 w-24" />
            <Bar className="h-6 w-2/3" />
            <Bar className="h-4 w-1/2" />
          </div>
          <Bar className="h-10 w-32 shrink-0" />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-lg lg:grid-cols-5">
        <div className="rounded-xl bg-surface-container p-lg lg:col-span-3">
          <Bar className="h-4 w-24" />
          <div className="mt-lg grid grid-cols-2 gap-md sm:grid-cols-4">
            <Bar className="h-12" />
            <Bar className="h-12" />
            <Bar className="h-12" />
            <Bar className="h-12" />
          </div>
          <Bar className="mt-lg h-32" />
        </div>
        <div className="rounded-xl bg-surface-container p-lg lg:col-span-2">
          <Bar className="h-4 w-24" />
          <Bar className="mt-lg h-52" />
          <Bar className="mt-md h-4 w-full" />
          <Bar className="mt-sm h-4 w-full" />
          <Bar className="mt-sm h-4 w-full" />
        </div>
      </div>
      <div className="rounded-xl bg-surface-container p-lg">
        <Bar className="h-4 w-24" />
        <Bar className="mt-lg h-56" />
      </div>
    </div>
  );
}
