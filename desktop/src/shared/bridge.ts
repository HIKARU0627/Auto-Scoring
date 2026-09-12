/**
 * The whole contract between the Electron main process and the renderer.
 *
 * The renderer has no Node and no Electron access (`contextIsolation: true`,
 * `nodeIntegration: false`, `sandbox: true`), so everything it can reach from
 * the main process passes through `window.autoScoring`, which the preload
 * script builds with `contextBridge.exposeInMainWorld`. Keeping the shape here
 * -- in a file that imports nothing -- is what lets `test/architecture.test.ts`
 * check the surface mechanically from both sides.
 *
 * **No raw bytes cross this boundary.** The Python sidecar owns `app-data`
 * (Issue #207 approval condition 3), so the renderer never receives a PDF's
 * bytes; it gets identifiers and URLs and asks the sidecar over HTTP for the
 * rest. `test/architecture.test.ts` fails if a binary payload type
 * (`ArrayBuffer`, `Buffer`, `Uint8Array`, `Blob`, ...) appears in this file, so
 * the rule is enforced rather than merely written down here.
 */

import type { BulkExportWriteRequest } from "./bulk-export-write.js";
import type { ScannedFolder } from "./folder-scan.js";
import type {
  MaterialWindowRequest,
  MaterialWindowSelection,
} from "./material-window.js";
import type {
  SidecarMultipartRequest,
  SidecarMultipartResponse,
} from "./sidecar-upload.js";
import type {
  SidecarFetchRequest,
  SidecarFetchResponse,
} from "./sidecar-fetch.js";

/** Identifies this build to the renderer. Placeholder surface for Phase 2. */
export interface AppInfo {
  /** The `version` field of `desktop/package.json`. */
  readonly version: string;
  /** `process.platform` of the main process, e.g. `win32`. */
  readonly platform: string;
}

/**
 * Why a sidecar is not available.
 *
 * Mirrors `core/sidecar_supervisor.dart` (SidecarFailure):
 * - executableMissing: Binary not found on disk.
 * - alreadyRunning: Another process holds app-data lock (exit code 3).
 * - exitedDuringStartup: Process exited before handshake/health succeeded.
 * - startupTimedOut: Process did not become healthy within 60s.
 * - crashed: Process terminated after having been ready.
 */
export type SidecarFailure =
  | "executableMissing"
  | "alreadyRunning"
  | "exitedDuringStartup"
  | "startupTimedOut"
  | "crashed";

/** Loopback connection details exposed to the renderer (no bearer token). */
export interface SidecarConnectionInfo {
  readonly host: string;
  readonly port: number;
}

/**
 * The current state of the Python sidecar.
 *
 * The bearer token never crosses this boundary (Issue #264). HTTP auth is
 * applied in the main process.
 */
export type SidecarStatus =
  | { readonly kind: "starting" }
  | { readonly kind: "ready"; readonly connection: SidecarConnectionInfo }
  | {
      readonly kind: "failed";
      readonly failure: SidecarFailure;
      readonly exitCode: number | null;
    }
  | { readonly kind: "stopped" };

/** Everything the preload script exposes on `window.autoScoring`. */
export interface AutoScoringBridge {
  getAppInfo(): Promise<AppInfo>;
  /**
   * The file the sidecar writes its rotating log to, for the crash screen to
   * name (UG-14). Resolved by the main process from the same app-data root the
   * sidecar uses, so the screen cannot point somewhere the log never reaches.
   */
  getSidecarLogPath(): Promise<string>;
  getSidecarStatus(): Promise<SidecarStatus>;
  restartSidecar(): Promise<void>;
  onSidecarStatusChange(callback: (status: SidecarStatus) => void): () => void;
  chooseFolder(): Promise<string | null>;
  choosePdfFile(): Promise<string | null>;
  /** UG-09 overwrite protection lives in main; the final name is returned. */
  bulkExportWriteFile(request: BulkExportWriteRequest): Promise<string>;
  bulkExportFileExists(
    directoryPath: string,
    fileName: string,
  ): Promise<boolean>;
  bulkExportReadFile(
    directoryPath: string,
    fileName: string,
  ): Promise<string | null>;
  scanFolder(directoryPath: string): Promise<ScannedFolder>;
  /**
   * Ask the main process to open (or re-focus) **the** material window and show
   * this test's materials (Issue #415). One window is reused; calling it again
   * replaces what it shows instead of opening another window. A renderer still
   * cannot open a window itself (`main.ts` keeps `setWindowOpenHandler` denying).
   */
  openMaterialWindow(request: MaterialWindowRequest): Promise<void>;
  /** What the material window is showing now, or `null` before anything asked. */
  getMaterialSelection(): Promise<MaterialWindowSelection | null>;
  onMaterialSelectionChange(
    callback: (selection: MaterialWindowSelection) => void,
  ): () => void;
  sidecarMultipartUpload(
    request: SidecarMultipartRequest,
  ): Promise<SidecarMultipartResponse>;
  sidecarFetch(request: SidecarFetchRequest): Promise<SidecarFetchResponse>;
  /**
   * Frameless-window controls (Issue #428). The OS frame is gone, so the
   * renderer draws its own title bar and asks the main process to act.
   *
   * **The target window is resolved from the IPC sender, never from an
   * argument.** There is no window id in this contract on purpose: a renderer
   * that could name another window would be able to minimize or close it, and
   * the renderer is untrusted. Each call acts on the window the requesting
   * `webContents` belongs to.
   */
  minimizeWindow(): Promise<void>;
  /** Maximize when normal, restore when maximized. */
  toggleMaximizeWindow(): Promise<void>;
  closeWindow(): Promise<void>;
  /** Whether the requesting window is currently maximized. */
  isWindowMaximized(): Promise<boolean>;
  /** Fires on maximize/restore of the requesting window. */
  onWindowMaximizedChange(callback: (maximized: boolean) => void): () => void;
  /**
   * Whether the requesting window currently has keyboard focus (Issue #446).
   *
   * The title bar dims on `blur` so two open windows can be told apart; the
   * renderer resolves the window from `event.sender` here too, so a renderer
   * cannot ask about (or be told about) another window's focus.
   */
  isWindowFocused(): Promise<boolean>;
  /** Fires on focus/blur of the requesting window. */
  onWindowFocusChange(callback: (focused: boolean) => void): () => void;
}

/** IPC channel names. One place, so main and preload cannot drift apart. */
export const IpcChannel = {
  getAppInfo: "auto-scoring:get-app-info",
  getSidecarLogPath: "auto-scoring:get-sidecar-log-path",
  getSidecarStatus: "auto-scoring:get-sidecar-status",
  restartSidecar: "auto-scoring:restart-sidecar",
  sidecarStatusChanged: "auto-scoring:sidecar-status-changed",
  chooseFolder: "auto-scoring:choose-folder",
  choosePdfFile: "auto-scoring:choose-pdf-file",
  bulkExportWriteFile: "auto-scoring:bulk-export-write-file",
  bulkExportFileExists: "auto-scoring:bulk-export-file-exists",
  bulkExportReadFile: "auto-scoring:bulk-export-read-file",
  scanFolder: "auto-scoring:scan-folder",
  openMaterialWindow: "auto-scoring:open-material-window",
  getMaterialSelection: "auto-scoring:get-material-selection",
  materialSelectionChanged: "auto-scoring:material-selection-changed",
  sidecarMultipartUpload: "auto-scoring:sidecar-multipart-upload",
  sidecarFetch: "auto-scoring:sidecar-fetch",
  minimizeWindow: "auto-scoring:minimize-window",
  toggleMaximizeWindow: "auto-scoring:toggle-maximize-window",
  closeWindow: "auto-scoring:close-window",
  isWindowMaximized: "auto-scoring:is-window-maximized",
  windowMaximizedChanged: "auto-scoring:window-maximized-changed",
  isWindowFocused: "auto-scoring:is-window-focused",
  windowFocusChanged: "auto-scoring:window-focus-changed",
} as const;

export type IpcChannelName = (typeof IpcChannel)[keyof typeof IpcChannel];
