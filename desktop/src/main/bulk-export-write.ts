import { promises as fs } from "node:fs";
import * as path from "node:path";

import type { BulkExportWriteRequest } from "../shared/bulk-export-write.js";

/**
 * Filesystem side of the bulk-export write path (Issue #345).
 *
 * The renderer is sandboxed and has no Node, so a chosen folder arrives as a
 * path and the bytes arrive base64-encoded. The main process is what actually
 * writes, and it is the single authority for UG-09: an existing file is never
 * overwritten, the new one moves to `_2`, `_3`, ... instead. Resolving that
 * here with `wx` keeps the guarantee even if two writers race.
 */

/** Keeps the renderer from naming a path; only the basename is used. */
export function sanitizeBulkExportFileName(fileName: string): string {
  const base = path.basename(fileName.trim());
  if (base.length === 0 || base === "." || base === "..") {
    return "export.pdf";
  }
  return base;
}

function suffixedFileName(fileName: string, counter: number): string {
  const dot = fileName.lastIndexOf(".");
  const stem = dot > 0 ? fileName.slice(0, dot) : fileName;
  const extension = dot > 0 ? fileName.slice(dot) : "";
  return `${stem}_${String(counter)}${extension}`;
}

/** Writes `request.bytesBase64` and returns the file name actually used. */
export async function writeBulkExportFile(
  request: BulkExportWriteRequest,
): Promise<string> {
  const bytes = Buffer.from(request.bytesBase64, "base64");
  const base = sanitizeBulkExportFileName(request.fileName);
  let candidate = base;
  let counter = 2;
  for (;;) {
    try {
      await fs.writeFile(path.join(request.directoryPath, candidate), bytes, {
        flag: "wx",
      });
      return candidate;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") {
        throw error;
      }
      candidate = suffixedFileName(base, counter);
      counter += 1;
    }
  }
}

/** Whether `fileName` already exists in `directoryPath` (UG-09 naming). */
export async function bulkExportFileExists(
  directoryPath: string,
  fileName: string,
): Promise<boolean> {
  try {
    await fs.access(
      path.join(directoryPath, sanitizeBulkExportFileName(fileName)),
    );
    return true;
  } catch {
    return false;
  }
}

/** Reads back a written file as base64, or `null` when it is gone. */
export async function readBulkExportFile(
  directoryPath: string,
  fileName: string,
): Promise<string | null> {
  try {
    const bytes = await fs.readFile(
      path.join(directoryPath, sanitizeBulkExportFileName(fileName)),
    );
    return bytes.toString("base64");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return null;
    }
    throw error;
  }
}
