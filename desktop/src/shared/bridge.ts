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

import type { ScannedFolder } from "./folder-scan.js";
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
  getSidecarStatus(): Promise<SidecarStatus>;
  restartSidecar(): Promise<void>;
  onSidecarStatusChange(callback: (status: SidecarStatus) => void): () => void;
  chooseFolder(): Promise<string | null>;
  scanFolder(directoryPath: string): Promise<ScannedFolder>;
  sidecarMultipartUpload(
    request: SidecarMultipartRequest,
  ): Promise<SidecarMultipartResponse>;
  sidecarFetch(request: SidecarFetchRequest): Promise<SidecarFetchResponse>;
}

/** IPC channel names. One place, so main and preload cannot drift apart. */
export const IpcChannel = {
  getAppInfo: "auto-scoring:get-app-info",
  getSidecarStatus: "auto-scoring:get-sidecar-status",
  restartSidecar: "auto-scoring:restart-sidecar",
  sidecarStatusChanged: "auto-scoring:sidecar-status-changed",
  chooseFolder: "auto-scoring:choose-folder",
  scanFolder: "auto-scoring:scan-folder",
  sidecarMultipartUpload: "auto-scoring:sidecar-multipart-upload",
  sidecarFetch: "auto-scoring:sidecar-fetch",
} as const;

export type IpcChannelName = (typeof IpcChannel)[keyof typeof IpcChannel];
