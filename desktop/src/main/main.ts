import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import * as path from "node:path";
import { IpcChannel, type AppInfo } from "../shared/bridge.js";
import type { ScannedFolder } from "../shared/folder-scan.js";
import type {
  SidecarMultipartRequest,
  SidecarMultipartResponse,
} from "../shared/sidecar-upload.js";
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
import { sidecarFetch } from "./sidecar-fetch.js";
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

function createWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1280,
    height: 800,
    // Painting an empty window before the renderer has anything to draw shows a
    // white flash on a dark theme, so the window is created hidden and revealed
    // on `ready-to-show`.
    show: false,
    webPreferences: {
      preload: PRELOAD_SCRIPT,
      // The three that make the renderer untrusted code. `test/architecture.test.ts`
      // fails if any of them is changed here, because the import rules it enforces
      // on `src/renderer` only mean anything while these hold.
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  window.once("ready-to-show", () => {
    window.show();
  });

  // A renderer must never be able to navigate the shell somewhere else or open a
  // second window of its own; anything the UI wants to open goes to the user's
  // real browser instead.
  window.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });

  if (devServerUrl !== undefined && devServerUrl !== "") {
    void window.loadURL(devServerUrl);
  } else {
    void window.loadFile(RENDERER_INDEX);
  }

  return window;
}

ipcMain.handle(IpcChannel.getAppInfo, (): AppInfo => {
  return { version: app.getVersion(), platform: process.platform };
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
  const override = process.env["AUTO_SCORING_E2E_FOLDER"];
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
  const override = process.env["AUTO_SCORING_E2E_PDF"];
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
  IpcChannel.scanFolder,
  async (_event, directoryPath: string): Promise<ScannedFolder> =>
    await scanDirectory(directoryPath),
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
  const appDataOverride = process.env["AUTO_SCORING_E2E_APP_DATA"];

  supervisor = new SidecarSupervisor({
    executablePath,
    appDataDirectory:
      appDataOverride !== undefined && appDataOverride.length > 0
        ? appDataOverride
        : null,
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
