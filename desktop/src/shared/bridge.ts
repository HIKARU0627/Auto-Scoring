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

/** Identifies this build to the renderer. Placeholder surface for Phase 2. */
export interface AppInfo {
  /** The `version` field of `desktop/package.json`. */
  readonly version: string;
  /** `process.platform` of the main process, e.g. `win32`. */
  readonly platform: string;
}

/** Everything the preload script exposes on `window.autoScoring`. */
export interface AutoScoringBridge {
  getAppInfo(): Promise<AppInfo>;
  chooseFolder(): Promise<string | null>;
  scanFolder(directoryPath: string): Promise<ScannedFolder>;
  sidecarMultipartUpload(
    request: SidecarMultipartRequest,
  ): Promise<SidecarMultipartResponse>;
}

/** IPC channel names. One place, so main and preload cannot drift apart. */
export const IpcChannel = {
  getAppInfo: "auto-scoring:get-app-info",
  chooseFolder: "auto-scoring:choose-folder",
  scanFolder: "auto-scoring:scan-folder",
  sidecarMultipartUpload: "auto-scoring:sidecar-multipart-upload",
} as const;

export type IpcChannelName = (typeof IpcChannel)[keyof typeof IpcChannel];
