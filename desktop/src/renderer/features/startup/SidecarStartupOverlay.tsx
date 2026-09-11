import type { JSX } from "react";

import type { SidecarFailure, SidecarStatus } from "../../../shared/bridge.js";

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

function failureDetail(failure: SidecarFailure): string {
  switch (failure) {
    case "executableMissing":
      return "インストーラーから再インストールしてください。";
    case "alreadyRunning":
      return "すでに開いているウィンドウをご利用ください。閉じた直後の場合は、少し待ってから再起動してください。";
    default:
      return "ログ: %LOCALAPPDATA%\\Auto-Scoring\\app-data\\logs\\sidecar.log";
  }
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
        <p className="text-body-small text-on-surface-variant">
          初回起動には時間がかかることがあります。
        </p>
      </div>
    </main>
  );
}

function SidecarErrorScreen({
  failure,
  exitCode,
  onRestart,
}: {
  failure: SidecarFailure;
  exitCode: number | null;
  onRestart: () => void;
}): JSX.Element {
  return (
    <main
      data-testid="sidecar-error"
      className="flex min-h-screen items-center justify-center bg-surface p-xl text-on-surface"
    >
      <div className="max-w-140 text-center">
        <span
          aria-hidden
          className="material-symbols-outlined text-5xl text-error"
        >
          error_outline
        </span>
        <h1 className="mt-lg text-title-medium">{failureHeadline(failure)}</h1>
        <p className="mt-md text-body-small text-on-surface-variant">
          {failureDetail(failure)}
        </p>
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
 * recoverable error screen when it has failed (INV-030, INV-032, INV-036).
 */
export function SidecarStartupOverlay({
  status,
  onRestart,
  children,
}: {
  status: SidecarStatus;
  onRestart: () => void;
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
      <div className="absolute inset-0 z-50">{overlay}</div>
    </div>
  );
}
