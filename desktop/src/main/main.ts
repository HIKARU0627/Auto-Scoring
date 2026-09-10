import { app, BrowserWindow, ipcMain, shell } from "electron";
import * as path from "node:path";
import { IpcChannel, type AppInfo, type SidecarStatus } from "../shared/bridge";
import {
  resolveSidecarExecutable,
  sidecarExecutableCandidates,
} from "./sidecar-paths";
import { SidecarSupervisor } from "./sidecar-supervisor";

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

function notifySidecarStatus(status: SidecarStatus): void {
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed()) {
      window.webContents.send(IpcChannel.sidecarStatusChanged, status);
    }
  }
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
  return supervisor?.status ?? { kind: "starting" };
});

ipcMain.handle(IpcChannel.restartSidecar, async (): Promise<void> => {
  await supervisor?.restart();
});

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
