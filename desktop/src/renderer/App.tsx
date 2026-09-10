import { useEffect, useState, type JSX } from "react";
import type { AppInfo } from "../shared/bridge";
import { useTheme } from "./theme/ThemeProvider";

/**
 * Placeholder root component. Issue #217 is the skeleton; the first real screen
 * (home) is a separate Issue, as are the design tokens it will be built from.
 *
 * It does one thing on purpose: read `window.autoScoring`, so the preload bridge
 * is exercised by something rather than only declared.
 */
export function App(): JSX.Element {
  const { theme, toggleTheme } = useTheme();
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    void window.autoScoring.getAppInfo().then((info) => {
      if (!cancelled) {
        setAppInfo(info);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="min-h-screen bg-surface p-xl text-on-surface">
      <h1 className="text-title-large font-medium leading-ui">Auto-Scoring</h1>
      <p className="mt-sm text-body-medium text-on-surface-variant">
        {appInfo === null
          ? "読み込み中…"
          : `version ${appInfo.version} / ${appInfo.platform}`}
      </p>
      <button
        type="button"
        className="mt-lg rounded-md border border-outline px-lg py-sm text-ui-label"
        onClick={toggleTheme}
      >
        テーマ: {theme === "dark" ? "ダーク" : "ライト"}
      </button>
    </main>
  );
}
