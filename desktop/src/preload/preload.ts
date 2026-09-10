import { contextBridge, ipcRenderer } from "electron";
import {
  IpcChannel,
  type AppInfo,
  type AutoScoringBridge,
} from "../shared/bridge.js";
import type { ScannedFolder } from "../shared/folder-scan.js";
import type {
  SidecarMultipartRequest,
  SidecarMultipartResponse,
} from "../shared/sidecar-upload.js";

/**
 * The only bridge between the main process and the renderer.
 *
 * Everything exposed here is listed in `src/shared/bridge.ts`. Nothing else is
 * reachable from the renderer: `ipcRenderer` itself is deliberately not exposed,
 * because handing it over would give the renderer every channel the main process
 * will ever register, including ones added long after this file was reviewed.
 *
 * **No raw bytes.** The sidecar owns `app-data` (Issue #207 approval condition 3),
 * so a PDF reaches the renderer as an identifier it can ask the sidecar about,
 * never as a byte array passed through IPC.
 */
const bridge: AutoScoringBridge = {
  getAppInfo: (): Promise<AppInfo> =>
    ipcRenderer.invoke(IpcChannel.getAppInfo) as Promise<AppInfo>,
  chooseFolder: (): Promise<string | null> =>
    ipcRenderer.invoke(IpcChannel.chooseFolder) as Promise<string | null>,
  scanFolder: (directoryPath: string): Promise<ScannedFolder> =>
    ipcRenderer.invoke(
      IpcChannel.scanFolder,
      directoryPath,
    ) as Promise<ScannedFolder>,
  sidecarMultipartUpload: (
    request: SidecarMultipartRequest,
  ): Promise<SidecarMultipartResponse> =>
    ipcRenderer.invoke(
      IpcChannel.sidecarMultipartUpload,
      request,
    ) as Promise<SidecarMultipartResponse>,
};

contextBridge.exposeInMainWorld("autoScoring", bridge);
