import type { AutoScoringBridge } from "../shared/bridge";

declare global {
  interface Window {
    /**
     * Installed by `src/preload/preload.ts` through `contextBridge`. It is the
     * renderer's only way out; there is no `require`, no `process` and no
     * `ipcRenderer` here (`contextIsolation: true`, `nodeIntegration: false`).
     */
    readonly autoScoring: AutoScoringBridge;
  }
}
