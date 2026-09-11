/**
 * IPC contract for writing a bulk-export PDF into a folder the user chose.
 *
 * Bytes cross the bridge as a base64 string for the same reason
 * `sidecar-fetch.ts` carries response bodies that way: `bridge.ts` must stay
 * free of binary payload types, which `test/architecture.test.ts` enforces.
 * The destination folder always comes from `chooseFolder`; the renderer does
 * not choose paths on its own.
 */

export interface BulkExportWriteRequest {
  /** The folder `window.autoScoring.chooseFolder` returned. */
  readonly directoryPath: string;
  /** The file name to write; a directory component is stripped in main. */
  readonly fileName: string;
  readonly bytesBase64: string;
}
