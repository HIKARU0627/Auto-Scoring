import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { MaterialWindowApp } from "./features/materials/MaterialWindowPage";
import { WindowTitleBar } from "./navigation/WindowTitleBar";
import { ThemeProvider } from "./theme/ThemeProvider";
import "./styles/index.css";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("index.html must contain #root");
}

/**
 * The material window loads this same bundle with `?window=material`
 * (`main.ts`). The query string, not a second HTML entry, is what keeps the
 * second window on the identical CSP and preload (Issue #415 decision 2).
 */
const isMaterialWindow =
  new URLSearchParams(window.location.search).get("window") === "material";

/**
 * Frameless windows (Issue #428): the OS caption is gone, so the app root is a
 * full-height column of "custom title bar (fixed) + everything else". Reserving
 * the band here, once, is what keeps its height out of `AppShell` and the
 * grading-unavailable banner; those fill the `flex-1` area they are given. The
 * height itself is owned by `WINDOW_TITLE_BAR_HEIGHT` (`WindowTitleBar`), so
 * there is no second copy of the number to keep in step (Issue #446).
 */
createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <div
        data-testid="window-frame"
        className="flex h-dvh flex-col overflow-hidden bg-surface"
      >
        <WindowTitleBar title={isMaterialWindow ? "資料" : "Auto-Scoring"} />
        <div
          data-testid="window-content"
          className="flex min-h-0 flex-1 flex-col overflow-auto"
        >
          {isMaterialWindow ? <MaterialWindowApp /> : <App />}
        </div>
      </div>
    </ThemeProvider>
  </StrictMode>,
);
