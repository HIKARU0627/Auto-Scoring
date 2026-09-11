import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import type { SidecarStatus } from "../../src/shared/bridge.js";
import { App } from "../../src/renderer/App";
import { ThemeProvider } from "../../src/renderer/theme/ThemeProvider";

const readyStatus: SidecarStatus = {
  kind: "ready",
  connection: { host: "127.0.0.1", port: 12345, token: "test-token" },
};

function stubBridge(statusRef: { current: SidecarStatus }) {
  const listeners = new Set<(status: SidecarStatus) => void>();

  vi.stubGlobal("autoScoring", {
    getAppInfo: vi.fn(async () => ({ version: "0.0.0", platform: "linux" })),
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

function renderApp() {
  return render(
    <ThemeProvider>
      <App />
    </ThemeProvider>,
  );
}

describe("App sidecar lifecycle wiring", () => {
  it("shows a splash while the sidecar is starting (INV-030)", async () => {
    const statusRef = { current: { kind: "starting" } as SidecarStatus };
    stubBridge(statusRef);
    renderApp();

    expect(await screen.findByTestId("sidecar-splash")).toBeDefined();
    expect(screen.getByText("バックエンドを起動しています…")).toBeDefined();
  });

  it("shows the home entry points once the sidecar is ready", async () => {
    const statusRef = { current: readyStatus };
    stubBridge(statusRef);
    renderApp();

    expect(await screen.findByTestId("home-open-intake")).toBeDefined();
    expect(screen.queryByTestId("sidecar-splash")).toBeNull();
  });

  it("offers restart on failure without exposing bearer tokens (INV-032, INV-036)", async () => {
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
});
