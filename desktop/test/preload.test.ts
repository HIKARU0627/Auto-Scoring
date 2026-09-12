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

  it("getSidecarLogPath invokes getSidecarLogPath IPC channel", async () => {
    mockIpcRenderer.invoke.mockResolvedValueOnce(
      "C:\\Users\\tester\\AppData\\Local\\Auto-Scoring\\app-data\\logs\\sidecar.log",
    );
    const result = await exposedBridge!.getSidecarLogPath();
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      "auto-scoring:get-sidecar-log-path",
    );
    expect(result).toBe(
      "C:\\Users\\tester\\AppData\\Local\\Auto-Scoring\\app-data\\logs\\sidecar.log",
    );
  });

  it("getSidecarStatus invokes getSidecarStatus IPC channel", async () => {
    const readyStatus: SidecarStatus = {
      kind: "ready",
      connection: { host: "127.0.0.1", port: 5000 },
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

  it("sidecarFetch invokes sidecarFetch IPC channel", async () => {
    mockIpcRenderer.invoke.mockResolvedValueOnce({
      status: 200,
      statusText: "OK",
      headers: {},
      bodyBase64: "",
    });
    const result = await exposedBridge!.sidecarFetch({
      method: "GET",
      urlPath: "/healthz",
    });
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      "auto-scoring:sidecar-fetch",
      { method: "GET", urlPath: "/healthz" },
    );
    expect(result.status).toBe(200);
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

  it("openMaterialWindow invokes openMaterialWindow IPC channel", async () => {
    mockIpcRenderer.invoke.mockResolvedValueOnce(undefined);

    await exposedBridge!.openMaterialWindow({ testId: "t1", materialId: "m1" });

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      "auto-scoring:open-material-window",
      { testId: "t1", materialId: "m1" },
    );
  });

  it("getMaterialSelection invokes getMaterialSelection IPC channel", async () => {
    mockIpcRenderer.invoke.mockResolvedValueOnce({
      testId: "t1",
      materialId: null,
    });

    const result = await exposedBridge!.getMaterialSelection();

    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      "auto-scoring:get-material-selection",
    );
    expect(result).toEqual({ testId: "t1", materialId: null });
  });

  it("minimizeWindow invokes minimizeWindow IPC channel", async () => {
    mockIpcRenderer.invoke.mockResolvedValueOnce(undefined);
    await exposedBridge!.minimizeWindow();
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      "auto-scoring:minimize-window",
    );
  });

  it("toggleMaximizeWindow invokes toggleMaximizeWindow IPC channel", async () => {
    mockIpcRenderer.invoke.mockResolvedValueOnce(undefined);
    await exposedBridge!.toggleMaximizeWindow();
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      "auto-scoring:toggle-maximize-window",
    );
  });

  it("closeWindow invokes closeWindow IPC channel", async () => {
    mockIpcRenderer.invoke.mockResolvedValueOnce(undefined);
    await exposedBridge!.closeWindow();
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      "auto-scoring:close-window",
    );
  });

  it("isWindowMaximized invokes isWindowMaximized IPC channel", async () => {
    mockIpcRenderer.invoke.mockResolvedValueOnce(true);
    const result = await exposedBridge!.isWindowMaximized();
    expect(mockIpcRenderer.invoke).toHaveBeenCalledWith(
      "auto-scoring:is-window-maximized",
    );
    expect(result).toBe(true);
  });

  it("onWindowMaximizedChange registers and unregisters IPC listener", () => {
    const callback = vi.fn();
    const unsubscribe = exposedBridge!.onWindowMaximizedChange(callback);

    expect(mockIpcRenderer.on).toHaveBeenCalledWith(
      "auto-scoring:window-maximized-changed",
      expect.any(Function),
    );

    const registeredListener = mockIpcRenderer.on.mock.calls[0]![1] as (
      event: unknown,
      maximized: boolean,
    ) => void;
    registeredListener({}, true);
    expect(callback).toHaveBeenCalledWith(true);

    unsubscribe();
    expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith(
      "auto-scoring:window-maximized-changed",
      registeredListener,
    );
  });

  it("onMaterialSelectionChange registers and unregisters IPC listener", () => {
    const callback = vi.fn();
    const unsubscribe = exposedBridge!.onMaterialSelectionChange(callback);

    expect(mockIpcRenderer.on).toHaveBeenCalledWith(
      "auto-scoring:material-selection-changed",
      expect.any(Function),
    );

    const registeredListener = mockIpcRenderer.on.mock.calls[0]![1] as (
      event: unknown,
      selection: { testId: string; materialId: string | null },
    ) => void;
    const selection = { testId: "t1", materialId: "m1" };
    registeredListener({}, selection);
    expect(callback).toHaveBeenCalledWith(selection);

    unsubscribe();
    expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith(
      "auto-scoring:material-selection-changed",
      registeredListener,
    );
  });
});
