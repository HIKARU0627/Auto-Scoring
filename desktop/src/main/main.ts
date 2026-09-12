import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import * as os from "node:os";
import * as path from "node:path";
import { IpcChannel, type AppInfo } from "../shared/bridge.js";
import type { ScannedFolder } from "../shared/folder-scan.js";
import type {
  MaterialWindowRequest,
  MaterialWindowSelection,
} from "../shared/material-window.js";
import type {
  SidecarMultipartRequest,
  SidecarMultipartResponse,
} from "../shared/sidecar-upload.js";
import type { BulkExportWriteRequest } from "../shared/bulk-export-write.js";
import {
  bulkExportFileExists,
  readBulkExportFile,
  writeBulkExportFile,
} from "./bulk-export-write.js";
import { scanDirectory } from "./folder-scan.js";
import {
  resolveSidecarExecutable,
  sidecarExecutableCandidates,
} from "./sidecar-paths";
import type { SidecarFetchRequest } from "../shared/sidecar-fetch.js";
import {
  getReadyConnection,
  toPublicSidecarStatus,
  type InternalSidecarStatus,
} from "./sidecar-connection.js";
import { readE2eEnv } from "./e2e-env.js";
import { sidecarFetch } from "./sidecar-fetch.js";
import { resolveSidecarAppDataDirectory } from "./sidecar-app-data.js";
import { resolveSidecarLogPath } from "./sidecar-log-path.js";
import { SidecarSupervisor } from "./sidecar-supervisor";
import { sidecarMultipartUpload } from "./sidecar-upload.js";
import type { SidecarStatus } from "../shared/bridge.js";

/**
 * Entry point of the Electron main process.
 *
 * Supervised Python sidecar lifecycle (Issue #234):
 * Spawns the sidecar, performs handshake, probes health, handles normal
 * shutdown before exit, supports restart, and arms parent PID watchdog.
 */

/** Compiled by `tsc` to `out/main/main.js`, so the siblings are one level up. */
const PRELOAD_SCRIPT = path.join(__dirname, "..", "preload", "preload.js");
const RENDERER_INDEX = path.join(__dirname, "..", "renderer", "index.html");

/**
 * Vite's dev server, when `pnpm run dev` starts one. Reading it here does not
 * repeat UG-05 (a release build must not take its start route or theme from the
 * environment): this only chooses between the dev server and the bundle that
 * shipped, and the packaged build has no dev server to point at.
 */
const devServerUrl = process.env["VITE_DEV_SERVER_URL"];

let supervisor: SidecarSupervisor | null = null;

function notifySidecarStatus(status: InternalSidecarStatus): void {
  const publicStatus = toPublicSidecarStatus(status);
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed()) {
      window.webContents.send(IpcChannel.sidecarStatusChanged, publicStatus);
    }
  }
}

function requireReadyConnection(): NonNullable<
  ReturnType<typeof getReadyConnection>
> {
  const connection = getReadyConnection(
    supervisor?.internalStatus ?? {
      kind: "starting",
    },
  );
  if (connection === null) {
    throw new Error("Sidecar is not ready");
  }
  return connection;
}

/**
 * Point a window at the shipped renderer (or Vite's dev server).
 *
 * `query` distinguishes the material window from the main one without a second
 * HTML entry or a second preload: both load the same bundle, and the bundle
 * reads `window=material` to decide which screen to mount. That is also what
 * keeps the material window on the same CSP as the main window (Issue #415).
 */
function loadRenderer(
  window: BrowserWindow,
  query?: Readonly<Record<string, string>>,
): void {
  if (devServerUrl !== undefined && devServerUrl !== "") {
    const url = new URL(devServerUrl);
    for (const [key, value] of Object.entries(query ?? {})) {
      url.searchParams.set(key, value);
    }
    void window.loadURL(url.toString());
    return;
  }
  void window.loadFile(RENDERER_INDEX, query === undefined ? {} : { query });
}

function untrustedWebPreferences(): Electron.WebPreferences {
  return {
    preload: PRELOAD_SCRIPT,
    // The three that make the renderer untrusted code. `test/architecture.test.ts`
    // fails if any of them is changed here, because the import rules it enforces
    // on `src/renderer` only mean anything while these hold. The material
    // window gets the same object, not a copy with one of them relaxed.
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
  };
}

/**
 * A renderer must never be able to navigate the shell somewhere else or open a
 * second window of its own; anything the UI wants to open goes to the user's
 * real browser instead. The material window is opened by the main process over
 * IPC, so this denial stays exactly as strict there (Issue #415 decision 1).
 */
function denyRendererWindows(window: BrowserWindow): void {
  window.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });
}

function createWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1280,
    height: 800,
    // Painting an empty window before the renderer has anything to draw shows a
    // white flash on a dark theme, so the window is created hidden and revealed
    // on `ready-to-show`.
    show: false,
    webPreferences: untrustedWebPreferences(),
  });

  window.once("ready-to-show", () => {
    window.show();
  });

  denyRendererWindows(window);

  // INV: closing the main window closes the material window with it (Issue #415
  // decision 4). Without this, the material window would keep the process alive
  // after the main window is gone -- especially on macOS, where
  // `window-all-closed` does not quit.
  window.on("closed", () => {
    if (materialWindow !== null && !materialWindow.isDestroyed()) {
      materialWindow.close();
    }
  });

  loadRenderer(window);

  return window;
}

/** The single material window, reused so materials never multiply windows. */
let materialWindow: BrowserWindow | null = null;

/** What the material window is showing, replayed to a window created later. */
let materialSelection: MaterialWindowSelection | null = null;

function createMaterialWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1100,
    height: 820,
    show: false,
    webPreferences: untrustedWebPreferences(),
  });

  window.once("ready-to-show", () => {
    window.show();
  });

  denyRendererWindows(window);

  window.on("closed", () => {
    materialWindow = null;
  });

  // A window created after a request still has to learn what to show. The
  // renderer also calls `getMaterialSelection` on mount, so an event that
  // arrives before its listener does cannot lose the selection.
  window.webContents.on("did-finish-load", () => {
    if (!window.isDestroyed() && materialSelection !== null) {
      window.webContents.send(
        IpcChannel.materialSelectionChanged,
        materialSelection,
      );
    }
  });

  loadRenderer(window, { window: "material" });

  return window;
}

function openMaterialWindow(request: MaterialWindowRequest): void {
  materialSelection = {
    testId: request.testId,
    materialId: request.materialId ?? null,
  };

  if (materialWindow !== null && !materialWindow.isDestroyed()) {
    if (materialWindow.isMinimized()) {
      materialWindow.restore();
    }
    materialWindow.focus();
    materialWindow.webContents.send(
      IpcChannel.materialSelectionChanged,
      materialSelection,
    );
    return;
  }

  materialWindow = createMaterialWindow();
}

ipcMain.handle(IpcChannel.getAppInfo, (): AppInfo => {
  return { version: app.getVersion(), platform: process.platform };
});

ipcMain.handle(IpcChannel.getSidecarLogPath, (): string => {
  // UG-14: resolved lazily from the same app-data root the supervisor uses, so
  // the crash screen's path and the sidecar's log file share one source.
  return resolveSidecarLogPath({
    isPackaged: app.isPackaged,
    env: process.env,
    platform: process.platform,
    homeDirectory: os.homedir(),
  });
});

ipcMain.handle(IpcChannel.getSidecarStatus, (): SidecarStatus => {
  return toPublicSidecarStatus(
    supervisor?.internalStatus ?? { kind: "starting" },
  );
});

ipcMain.handle(IpcChannel.restartSidecar, async (): Promise<void> => {
  await supervisor?.restart();
});

ipcMain.handle(IpcChannel.chooseFolder, async (): Promise<string | null> => {
  const override = readE2eEnv("AUTO_SCORING_E2E_FOLDER");
  if (override !== undefined && override.length > 0) {
    return override;
  }
  const result = await dialog.showOpenDialog({
    properties: ["openDirectory"],
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0] ?? null;
});

ipcMain.handle(IpcChannel.choosePdfFile, async (): Promise<string | null> => {
  const override = readE2eEnv("AUTO_SCORING_E2E_PDF");
  if (override !== undefined && override.length > 0) {
    return override;
  }
  const result = await dialog.showOpenDialog({
    properties: ["openFile"],
    filters: [{ name: "PDF", extensions: ["pdf"] }],
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0] ?? null;
});

ipcMain.handle(
  IpcChannel.bulkExportWriteFile,
  async (_event, request: BulkExportWriteRequest): Promise<string> =>
    await writeBulkExportFile(request),
);

ipcMain.handle(
  IpcChannel.bulkExportFileExists,
  async (_event, directoryPath: string, fileName: string): Promise<boolean> =>
    await bulkExportFileExists(directoryPath, fileName),
);

ipcMain.handle(
  IpcChannel.bulkExportReadFile,
  async (
    _event,
    directoryPath: string,
    fileName: string,
  ): Promise<string | null> =>
    await readBulkExportFile(directoryPath, fileName),
);

ipcMain.handle(
  IpcChannel.scanFolder,
  async (_event, directoryPath: string): Promise<ScannedFolder> =>
    await scanDirectory(directoryPath),
);

ipcMain.handle(
  IpcChannel.openMaterialWindow,
  (_event, request: MaterialWindowRequest): void => {
    openMaterialWindow(request);
  },
);

ipcMain.handle(
  IpcChannel.getMaterialSelection,
  (): MaterialWindowSelection | null => materialSelection,
);

ipcMain.handle(
  IpcChannel.sidecarMultipartUpload,
  async (
    _event,
    request: SidecarMultipartRequest,
  ): Promise<SidecarMultipartResponse> =>
    await sidecarMultipartUpload(requireReadyConnection(), request),
);

ipcMain.handle(
  IpcChannel.sidecarFetch,
  async (_event, request: SidecarFetchRequest) =>
    await sidecarFetch(requireReadyConnection(), request),
);

void app.whenReady().then(() => {
  const isWindows = process.platform === "win32";
  const candidates = sidecarExecutableCandidates({
    resolvedExecutable: process.execPath,
    workingDirectory: process.cwd(),
    isWindows,
  });
  const executablePath = resolveSidecarExecutable(candidates);

  supervisor = new SidecarSupervisor({
    executablePath,
    appDataDirectory: resolveSidecarAppDataDirectory({
      isPackaged: app.isPackaged,
      env: process.env,
    }),
    onStatusChange: (status) => {
      notifySidecarStatus(status);
    },
  });

  void supervisor.start();
  createWindow();

  // macOS keeps the process alive with no windows; clicking the dock icon has
  // to be able to bring one back.
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

let isQuitting = false;

// INV-031: Terminate sidecar before window/app exit
app.on("before-quit", (event) => {
  if (!isQuitting && supervisor) {
    event.preventDefault();
    isQuitting = true;
    supervisor.shutdown().finally(() => {
      app.quit();
    });
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

process.on("SIGINT", () => {
  if (supervisor) {
    void supervisor.shutdown().finally(() => process.exit(0));
  } else {
    process.exit(0);
  }
});

process.on("SIGTERM", () => {
  if (supervisor) {
    void supervisor.shutdown().finally(() => process.exit(0));
  } else {
    process.exit(0);
  }
});
