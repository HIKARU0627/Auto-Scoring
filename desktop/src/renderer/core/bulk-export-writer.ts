/**
 * Bulk export file naming and write helpers (Issue #142 / UG-09).
 *
 * Renderer-safe: no Node imports. Storage is injected so Vitest can observe
 * overwrite behaviour without a real folder.
 */

export interface BulkExportStorage {
  exists(fileName: string): Promise<boolean>;
  read(fileName: string): Promise<Uint8Array | null>;
  /** Returns the name actually written; main may suffix to avoid overwriting. */
  write(fileName: string, bytes: Uint8Array): Promise<string>;
}

/**
 * The slice of `window.autoScoring` the path-backed storage needs.
 *
 * Declared structurally (rather than importing the whole bridge) so the writer
 * stays testable with a fake and `core` does not depend on the preload surface.
 */
export interface BulkExportPathBridge {
  bulkExportFileExists(
    directoryPath: string,
    fileName: string,
  ): Promise<boolean>;
  bulkExportReadFile(
    directoryPath: string,
    fileName: string,
  ): Promise<string | null>;
  bulkExportWriteFile(request: {
    readonly directoryPath: string;
    readonly fileName: string;
    readonly bytesBase64: string;
  }): Promise<string>;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function base64ToBytes(base64: string): Uint8Array {
  return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
}

/**
 * Picks a file name that does not already exist in [storage].
 * Collisions become `_2`, `_3`, … — never overwrite (UG-09).
 */
export async function resolveFreeExportPath(
  fileName: string,
  exists: (fileName: string) => Promise<boolean>,
): Promise<string> {
  const dotIndex = fileName.lastIndexOf(".");
  const stem = dotIndex > 0 ? fileName.slice(0, dotIndex) : fileName;
  const extension = dotIndex > 0 ? fileName.slice(dotIndex) : "";
  let candidate = fileName;
  let counter = 2;
  while (await exists(candidate)) {
    candidate = `${stem}_${String(counter)}${extension}`;
    counter += 1;
  }
  return candidate;
}

export async function writeBulkExportFile(
  storage: BulkExportStorage,
  fileName: string,
  bytes: Uint8Array,
): Promise<string> {
  const freeName = await resolveFreeExportPath(fileName, (name) =>
    storage.exists(name),
  );
  return await storage.write(freeName, bytes);
}

/** In-memory storage for widget tests and UG-09 assertions. */
export function createMemoryBulkExportStorage(
  initial: Readonly<Record<string, Uint8Array>> = {},
): BulkExportStorage {
  const files = new Map<string, Uint8Array>(
    Object.entries(initial).map(([name, bytes]) => [
      name,
      new Uint8Array(bytes),
    ]),
  );
  return {
    exists: async (fileName) => files.has(fileName),
    read: async (fileName) => files.get(fileName) ?? null,
    write: async (fileName, bytes) => {
      files.set(fileName, new Uint8Array(bytes));
      return fileName;
    },
  };
}

/**
 * Production write target: a folder path returned by `chooseFolder`.
 *
 * All filesystem work happens in the main process (Issue #345). This is what
 * makes `AUTO_SCORING_E2E_FOLDER` reach the bulk export the same way it already
 * reaches intake: both go through `window.autoScoring.chooseFolder`.
 */
export function createPathBulkExportStorage(
  directoryPath: string,
  bridge: BulkExportPathBridge,
): BulkExportStorage {
  return {
    exists: (fileName) => bridge.bulkExportFileExists(directoryPath, fileName),
    read: async (fileName) => {
      const base64 = await bridge.bulkExportReadFile(directoryPath, fileName);
      return base64 === null ? null : base64ToBytes(base64);
    },
    write: (fileName, bytes) =>
      bridge.bulkExportWriteFile({
        directoryPath,
        fileName,
        bytesBase64: bytesToBase64(bytes),
      }),
  };
}

export function bulkExportFileName(exportFilePath: string): string {
  const parts = exportFilePath.split("/");
  return parts[parts.length - 1] ?? exportFilePath;
}
