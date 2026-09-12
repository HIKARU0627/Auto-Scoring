import { useEffect, useState, type JSX } from "react";

import type { SidecarFailure, SidecarStatus } from "../../../shared/bridge.js";
import { MaterialSymbolIcon } from "../../core/MaterialSymbolIcon.js";

/**
 * How long the splash waits before telling the user why it is slow (UG-15).
 *
 * Gated on elapsed time rather than shown always: a start that finishes in
 * 300ms does not need an explanation, and a notice that appears instantly is
 * read as decoration. 5s is comfortably past a warm start and well inside the
 * 12-15s measured for a first start with migrations (UG-08 allows 60s).
 */
export const SLOW_START_HINT_DELAY_MS = 5_000;

function failureHeadline(failure: SidecarFailure): string {
  switch (failure) {
    case "executableMissing":
      return "バックエンドが見つかりません。インストールが壊れている可能性があります。";
    case "alreadyRunning":
      return "Auto-Scoring はすでに起動しています。";
    case "exitedDuringStartup":
      return "バックエンドの起動に失敗しました。";
    case "startupTimedOut":
      return "バックエンドが時間内に応答しませんでした。";
    case "crashed":
      return "バックエンドが予期せず終了しました。";
  }
}

/**
 * The one line the user can act on per failure. `null` when the only thing to
 * say is the log location and it has not arrived from the main process yet.
 */
function failureDetail(
  failure: SidecarFailure,
  logPath: string | null,
): string | null {
  switch (failure) {
    case "executableMissing":
      return "インストーラーから再インストールしてください。";
    case "alreadyRunning":
      return "すでに開いているウィンドウをご利用ください。閉じた直後の場合は、少し待ってから再起動してください。";
    default:
      return logPath === null ? null : `ログ: ${logPath}`;
  }
}

/**
 * The first-launch hint (UG-15), shown only once the start has taken long
 * enough to look like a hang. Rendered from inside the splash so unmounting
 * the splash (the sidecar became ready) clears the timer.
 */
function SlowStartHint(): JSX.Element | null {
  const [elapsed, setElapsed] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setElapsed(true), SLOW_START_HINT_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);

  if (!elapsed) {
    return null;
  }

  return (
    <p
      data-testid="sidecar-slow-start-hint"
      className="text-body-small text-on-surface-variant"
    >
      初回起動には時間がかかることがあります。
    </p>
  );
}

function SidecarSplash({
  message = "バックエンドを起動しています…",
}: {
  message?: string;
}): JSX.Element {
  return (
    <main
      data-testid="sidecar-splash"
      className="flex min-h-screen items-center justify-center bg-surface text-on-surface"
    >
      <div className="flex flex-col items-center gap-xl px-xl text-center">
        <h1 className="text-title-large font-medium leading-ui">
          Auto-Scoring
        </h1>
        <div
          aria-hidden
          className="size-8 animate-spin rounded-full border-2 border-outline border-t-primary"
        />
        <p className="text-body-medium">{message}</p>
        <SlowStartHint />
      </div>
    </main>
  );
}

function SidecarErrorScreen({
  failure,
  exitCode,
  logPath,
  onRestart,
}: {
  failure: SidecarFailure;
  exitCode: number | null;
  logPath: string | null;
  onRestart: () => void;
}): JSX.Element {
  const detail = failureDetail(failure, logPath);
  return (
    <main
      data-testid="sidecar-error"
      className="flex min-h-screen items-center justify-center bg-surface p-xl text-on-surface"
    >
      <div className="max-w-140 text-center">
        <MaterialSymbolIcon
          name="error_outline"
          label="エラー"
          className="inline-block text-5xl text-error"
        />
        <h1 className="mt-lg text-title-medium">{failureHeadline(failure)}</h1>
        {detail !== null ? (
          <p
            data-testid="sidecar-error-detail"
            className="mt-md text-body-small text-on-surface-variant"
          >
            {detail}
          </p>
        ) : null}
        {exitCode !== null ? (
          <p className="mt-xs text-body-small text-on-surface-variant">
            終了コード: {exitCode}
          </p>
        ) : null}
        <button
          type="button"
          data-testid="sidecar-error-restart"
          className="mt-xl rounded-md bg-primary px-lg py-sm text-ui-label text-on-primary"
          onClick={onRestart}
        >
          再起動
        </button>
      </div>
    </main>
  );
}

/**
 * Covers the app while the sidecar is not usable: splash during startup and a
 * recoverable error screen when it has failed (INV-030, INV-032, INV-033,
 * INV-036, UG-14, UG-15).
 *
 * `children` stays mounted underneath rather than being replaced, so a crash
 * after the reviewer pushed a screen does not tear their route apart, and the
 * overlay is a sibling of the whole routed subtree -- which is what keeps it
 * visible over any depth of `push`.
 */
export function SidecarStartupOverlay({
  status,
  onRestart,
  logPath = null,
  children,
}: {
  status: SidecarStatus;
  onRestart: () => void;
  logPath?: string | null;
  children: JSX.Element;
}): JSX.Element {
  const overlay = (() => {
    switch (status.kind) {
      case "ready":
        return null;
      case "starting":
        return <SidecarSplash />;
      case "stopped":
        return <SidecarSplash message="終了しています…" />;
      case "failed":
        return (
          <SidecarErrorScreen
            failure={status.failure}
            exitCode={status.exitCode}
            logPath={logPath}
            onRestart={onRestart}
          />
        );
    }
  })();

  if (overlay === null) {
    return children;
  }

  return (
    <div className="relative min-h-screen">
      {children}
      <div data-testid="sidecar-overlay" className="absolute inset-0 z-50">
        {overlay}
      </div>
    </div>
  );
}
