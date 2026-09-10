import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AutoScoringBridge, SidecarStatus } from "../src/shared/bridge";

describe("preload script bridge", () => {
  let exposedBridge: AutoScoringBridge | null = null;
  const mockIpcRenderer = {
    invoke: vi.fn(),
    on: vi.fn(),
    removeListener: vi.fn(),
  };

  beforeEach(async () => {
    vi.resetModules();
    exposedBridge = null;
    mockIpcRenderer.invoke.mockReset();
    mockIpcRenderer.on.mockReset();
    mockIpcRenderer.removeListener.mockReset();

    vi.doMock("electron", () => ({
      contextBridge: {
        exposeInMainWorld: (_key: string, value: AutoScoringBridge) => {
          exposedBridge = value;
        },
      },
      ipcRenderer: mockIpcRenderer,
    }));

    await import("../src/preload/preload");
  });

  it("exposes autoScoring bridge into main world", () => {
    expect(exposedBridge).not.toBeNull();
  });

  it("getAppInfo invokes getAppInfo IPC channel", async () => {
    mockIpcRenderer.invoke.mockResolvedValueOnce({
      version: "0.1.0",
      platform: "linux",
    });
    const result = await exposedBridge!.getAppInfo();
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      "auto-scoring:get-app-info",
    );
    expect(result).toEqual({ version: "0.1.0", platform: "linux" });
  });

  it("getSidecarStatus invokes getSidecarStatus IPC channel", async () => {
    const readyStatus: SidecarStatus = {
      kind: "ready",
      connection: { host: "127.0.0.1", port: 5000, token: "tok" },
    };
    mockIpcRenderer.invoke.mockResolvedValueOnce(readyStatus);
    const result = await exposedBridge!.getSidecarStatus();
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      "auto-scoring:get-sidecar-status",
    );
    expect(result).toEqual(readyStatus);
  });

  it("restartSidecar invokes restartSidecar IPC channel", async () => {
    mockIpcRenderer.invoke.mockResolvedValueOnce(undefined);
    await exposedBridge!.restartSidecar();
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      "auto-scoring:restart-sidecar",
    );
  });

  it("onSidecarStatusChange registers and unregisters IPC listener", () => {
    const callback = vi.fn();
    const unsubscribe = exposedBridge!.onSidecarStatusChange(callback);

    expect(mockIpcRenderer.on).toHaveBeenCalledWith(
      "auto-scoring:sidecar-status-changed",
      expect.any(Function),
    );

    const registeredListener = mockIpcRenderer.on.mock.calls[0]![1] as (
      event: unknown,
      status: SidecarStatus,
    ) => void;

    // Simulate event from main process
    const testStatus: SidecarStatus = { kind: "starting" };
    registeredListener({}, testStatus);
    expect(callback).toHaveBeenCalledWith(testStatus);

    // Call unsubscribe
    unsubscribe();
    expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith(
      "auto-scoring:sidecar-status-changed",
      registeredListener,
    );
  });
});
