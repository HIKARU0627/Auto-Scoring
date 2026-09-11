import { contextBridge, ipcRenderer } from "electron";
import {
  IpcChannel,
  type AppInfo,
  type AutoScoringBridge,
  type SidecarStatus,
} from "../shared/bridge.js";
import type { ScannedFolder } from "../shared/folder-scan.js";
import type {
  SidecarHttpRequest,
  SidecarHttpResponse,
} from "../shared/sidecar-http.js";
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
  getSidecarStatus: (): Promise<SidecarStatus> =>
    ipcRenderer.invoke(IpcChannel.getSidecarStatus) as Promise<SidecarStatus>,
  restartSidecar: (): Promise<void> =>
    ipcRenderer.invoke(IpcChannel.restartSidecar) as Promise<void>,
  onSidecarStatusChange: (
    callback: (status: SidecarStatus) => void,
  ): (() => void) => {
    const listener = (
      _event: Electron.IpcRendererEvent,
      status: SidecarStatus,
    ) => {
      callback(status);
    };
    ipcRenderer.on(IpcChannel.sidecarStatusChanged, listener);
    return () => {
      ipcRenderer.removeListener(IpcChannel.sidecarStatusChanged, listener);
    };
  },
  chooseFolder: (): Promise<string | null> =>
    ipcRenderer.invoke(IpcChannel.chooseFolder) as Promise<string | null>,
  choosePdfFile: (): Promise<string | null> =>
    ipcRenderer.invoke(IpcChannel.choosePdfFile) as Promise<string | null>,
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
  sidecarFetch: (request: SidecarHttpRequest): Promise<SidecarHttpResponse> =>
    ipcRenderer.invoke(
      IpcChannel.sidecarFetch,
      request,
    ) as Promise<SidecarHttpResponse>,
};

contextBridge.exposeInMainWorld("autoScoring", bridge);
