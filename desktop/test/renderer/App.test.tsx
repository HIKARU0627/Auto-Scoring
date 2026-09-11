import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";

import type { SidecarStatus } from "../../src/shared/bridge.js";
import { App } from "../../src/renderer/App";
import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { SLOW_START_HINT_DELAY_MS } from "../../src/renderer/features/startup/SidecarStartupOverlay.js";
import { ThemeProvider } from "../../src/renderer/theme/ThemeProvider";

const readyStatus: SidecarStatus = {
  kind: "ready",
  connection: { host: "127.0.0.1", port: 12345 },
};

/**
 * A path that could not be produced by the renderer's own hard-coded default,
 * so a test finding it proves the screen rendered the bridge value instead
 * (UG-14).
 */
const logPathFromMain =
  "C:\\Users\\tester\\AppData\\Local\\Auto-Scoring\\app-data\\logs\\sidecar.log";

function stubBridge(statusRef: { current: SidecarStatus }) {
  const listeners = new Set<(status: SidecarStatus) => void>();

  vi.stubGlobal("autoScoring", {
    getAppInfo: vi.fn(async () => ({ version: "0.0.0", platform: "linux" })),
    getSidecarLogPath: vi.fn(async () => logPathFromMain),
    getSidecarStatus: vi.fn(async () => statusRef.current),
    restartSidecar: vi.fn(async () => {
      statusRef.current = { kind: "starting" };
      for (const listener of listeners) {
        listener(statusRef.current);
      }
    }),
    onSidecarStatusChange: vi.fn(
      (callback: (status: SidecarStatus) => void) => {
        listeners.add(callback);
        return () => {
          listeners.delete(callback);
        };
      },
    ),
    chooseFolder: vi.fn(async () => null),
    scanFolder: vi.fn(async () => ({ name: "batch", entries: [] })),
    sidecarMultipartUpload: vi.fn(async () => ({ status: 200, body: {} })),
    sidecarFetch: vi.fn(async () => ({
      status: 200,
      statusText: "OK",
      headers: {},
      bodyBase64: "",
    })),
  });

  return {
    emit(status: SidecarStatus) {
      statusRef.current = status;
      for (const listener of listeners) {
        listener(status);
      }
    },
  };
}

function renderApp(initialStack?: readonly string[]) {
  return render(
    <ThemeProvider>
      <App initialStack={initialStack} />
    </ThemeProvider>,
  );
}

describe("App sidecar lifecycle wiring", () => {
  it("shows a splash while the sidecar is starting (INV-030)", async () => {
    const statusRef = { current: { kind: "starting" } as SidecarStatus };
    stubBridge(statusRef);
    renderApp();

    const splash = await screen.findByTestId("sidecar-splash");
    expect(
      within(splash).getByRole("heading", { name: "Auto-Scoring" }),
    ).toBeDefined();
    expect(screen.getByText("バックエンドを起動しています…")).toBeDefined();
    // UG-15: the wait explains itself only once it is actually long. The
    // instant-time case is pinned here without fake timers; the delayed case
    // is below, and both are in Vitest because a real splash is transient
    // (Issue #288, docs/quality-gates.md).
    expect(screen.queryByTestId("sidecar-slow-start-hint")).toBeNull();
  });

  it("explains a slow first start only after the wait grows (UG-15)", async () => {
    vi.useFakeTimers();
    try {
      const statusRef = { current: { kind: "starting" } as SidecarStatus };
      stubBridge(statusRef);
      renderApp();
      await act(async () => {
        await Promise.resolve();
      });

      expect(screen.getByTestId("sidecar-splash")).toBeDefined();
      expect(screen.queryByTestId("sidecar-slow-start-hint")).toBeNull();

      act(() => {
        vi.advanceTimersByTime(SLOW_START_HINT_DELAY_MS);
      });

      expect(
        screen.getByTestId("sidecar-slow-start-hint").textContent,
      ).toContain("初回起動には時間がかかることがあります。");
    } finally {
      vi.useRealTimers();
    }
  });

  it("never shows the slow-start hint once the sidecar is ready (UG-15)", async () => {
    vi.useFakeTimers();
    try {
      const statusRef = { current: { kind: "starting" } as SidecarStatus };
      const bridge = stubBridge(statusRef);
      renderApp();
      await act(async () => {
        await Promise.resolve();
      });

      // Ready in under the threshold: the splash unmounts before its timer
      // fires, so no explanation is ever shown for a fast start.
      act(() => {
        bridge.emit(readyStatus);
      });
      act(() => {
        vi.advanceTimersByTime(SLOW_START_HINT_DELAY_MS * 2);
      });

      expect(screen.queryByTestId("sidecar-splash")).toBeNull();
      expect(screen.queryByTestId("sidecar-slow-start-hint")).toBeNull();
      expect(screen.getByTestId("home-open-intake")).toBeDefined();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the home entry points once the sidecar is ready", async () => {
    const statusRef = { current: readyStatus };
    stubBridge(statusRef);
    renderApp();

    expect(await screen.findByTestId("home-open-intake")).toBeDefined();
    expect(screen.queryByTestId("sidecar-splash")).toBeNull();
  });

  it("offers restart on failure and names the log from the main process (INV-032, UG-14)", async () => {
    const statusRef = {
      current: {
        kind: "failed",
        failure: "exitedDuringStartup",
        exitCode: 1,
      } as SidecarStatus,
    };
    stubBridge(statusRef);
    renderApp();

    expect(await screen.findByTestId("sidecar-error")).toBeDefined();
    expect(
      screen.getByText("バックエンドの起動に失敗しました。"),
    ).toBeDefined();
    expect(screen.getByText("終了コード: 1")).toBeDefined();
    expect(screen.getByTestId("sidecar-error-restart")).toBeDefined();

    // UG-14: the path is the value the main process reported, not a literal
    // the renderer keeps. The renderer is not able to produce this string on
    // its own, so finding it here is the check.
    expect(
      (await screen.findByTestId("sidecar-error-detail")).textContent,
    ).toContain(`ログ: ${logPathFromMain}`);

    const body = document.body.textContent ?? "";
    expect(body).not.toContain("Bearer");
    expect(body).not.toContain("test-token");
  });

  it("returns to the splash after pressing 再起動", async () => {
    const statusRef = {
      current: {
        kind: "failed",
        failure: "exitedDuringStartup",
        exitCode: 1,
      } as SidecarStatus,
    };
    const bridge = stubBridge(statusRef);
    renderApp();

    fireEvent.click(await screen.findByTestId("sidecar-error-restart"));
    bridge.emit({ kind: "starting" });

    expect(await screen.findByTestId("sidecar-splash")).toBeDefined();
  });

  it("keeps the crash overlay above a pushed screen, not only home (INV-033)", async () => {
    const statusRef = { current: readyStatus };
    const bridge = stubBridge(statusRef);
    // Home is at the bottom of the stack; `/starting` was pushed on top. If the
    // overlay lived inside the router as home, this depth would bury it.
    renderApp([AppRoutes.home, AppRoutes.starting]);

    expect(await screen.findByTestId("route-starting")).toBeDefined();

    bridge.emit({ kind: "failed", failure: "crashed", exitCode: null });

    expect(await screen.findByTestId("sidecar-error")).toBeDefined();
    expect(screen.getByTestId("sidecar-error-restart")).toBeDefined();

    // The overlay is a sibling over the whole routed subtree -- opaque and on
    // top -- rather than another route the pushed screen could cover.
    const layer = screen.getByTestId("sidecar-overlay");
    expect(layer.contains(screen.getByTestId("sidecar-error"))).toBe(true);
    expect(layer.className).toContain("absolute");
    expect(layer.className).toContain("inset-0");
    expect(layer.className).toContain("z-50");
  });

  it("restarts from a crash over a pushed screen (INV-033)", async () => {
    const statusRef = { current: readyStatus };
    const bridge = stubBridge(statusRef);
    renderApp([AppRoutes.home, AppRoutes.starting]);
    await screen.findByTestId("route-starting");

    bridge.emit({ kind: "failed", failure: "crashed", exitCode: null });
    fireEvent.click(await screen.findByTestId("sidecar-error-restart"));

    expect(await screen.findByTestId("sidecar-splash")).toBeDefined();
  });
});
