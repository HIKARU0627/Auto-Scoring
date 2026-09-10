/**
 * Bulk export file naming and write helpers (Issue #142 / UG-09).
 *
 * Renderer-safe: no Node imports. Storage is injected so Vitest can observe
 * overwrite behaviour without a real folder.
 */

export interface BulkExportStorage {
  exists(fileName: string): Promise<boolean>;
  read(fileName: string): Promise<Uint8Array | null>;
  write(fileName: string, bytes: Uint8Array): Promise<void>;
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
  await storage.write(freeName, bytes);
  return freeName;
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
    },
  };
}

/** Production write target via the File System Access API. */
export function createDirectoryHandleStorage(
  handle: FileSystemDirectoryHandle,
): BulkExportStorage {
  return {
    exists: async (fileName) => {
      try {
        await handle.getFileHandle(fileName);
        return true;
      } catch {
        return false;
      }
    },
    read: async (fileName) => {
      try {
        const fileHandle = await handle.getFileHandle(fileName);
        const file = await fileHandle.getFile();
        return new Uint8Array(await file.arrayBuffer());
      } catch {
        return null;
      }
    },
    write: async (fileName, bytes) => {
      const fileHandle = await handle.getFileHandle(fileName, { create: true });
      const writable = await fileHandle.createWritable();
      await writable.write(new Uint8Array(bytes));
      await writable.close();
    },
  };
}

export function bulkExportFileName(exportFilePath: string): string {
  const parts = exportFilePath.split("/");
  return parts[parts.length - 1] ?? exportFilePath;
}
