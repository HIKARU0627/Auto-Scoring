import { app, BrowserWindow, ipcMain, shell } from "electron";
import * as path from "node:path";
import { IpcChannel, type AppInfo } from "../shared/bridge";

/**
 * Entry point of the Electron main process.
 *
 * Phase 2-1 (Issue #217) is the skeleton only: it opens one window with a
 * placeholder renderer. No screen, no sidecar supervision (that follows PoC 7 /
 * Issue #203), no API client.
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

void app.whenReady().then(() => {
  createWindow();

  // macOS keeps the process alive with no windows; clicking the dock icon has
  // to be able to bring one back.
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
