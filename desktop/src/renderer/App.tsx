import { useEffect, useState, type JSX } from "react";
import type { AppInfo } from "../shared/bridge";

/**
 * Placeholder root component. Issue #217 is the skeleton; the first real screen
 * (home) is a separate Issue, as are the design tokens it will be built from.
 *
 * It does one thing on purpose: read `window.autoScoring`, so the preload bridge
 * is exercised by something rather than only declared.
 */
export function App(): JSX.Element {
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
    <main>
      <h1>Auto-Scoring</h1>
      <p>
        {appInfo === null
          ? "読み込み中…"
          : `version ${appInfo.version} / ${appInfo.platform}`}
      </p>
    </main>
  );
}
