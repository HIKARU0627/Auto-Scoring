import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import * as fs from "node:fs/promises";
import * as path from "node:path";

import {
  FolderTooLargeException,
  IGNORED_FILE_NAMES,
  MAX_SCANNED_FILES,
  type ScanDirectoryOptions,
  type ScannedEntry,
  type ScannedFolder,
} from "../shared/folder-scan.js";

async function sha256OfFile(filePath: string): Promise<string> {
  return await new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(filePath);
    stream.on("data", (chunk) => {
      hash.update(chunk);
    });
    stream.on("end", () => {
      resolve(hash.digest("hex"));
    });
    stream.on("error", reject);
  });
}

function shouldSkipFile(name: string): boolean {
  if (name.startsWith(".")) {
    return true;
  }
  return IGNORED_FILE_NAMES.has(name.toLowerCase());
}

/**
 * Walks [directoryPath] recursively, hashes each file via streaming read
 * (UG-12), and returns metadata only.
 */
export async function scanDirectory(
  directoryPath: string,
  options?: ScanDirectoryOptions,
): Promise<ScannedFolder> {
  const maxScannedFiles = options?.maxScannedFiles ?? MAX_SCANNED_FILES;
  const entries: ScannedEntry[] = [];

  async function walk(current: string): Promise<void> {
    const children = await fs.readdir(current, { withFileTypes: true });
    for (const child of children) {
      const absolute = path.join(current, child.name);
      if (child.isDirectory()) {
        await walk(absolute);
        continue;
      }
      if (!child.isFile()) {
        continue;
      }
      if (shouldSkipFile(child.name)) {
        continue;
      }
      if (entries.length >= maxScannedFiles) {
        throw new FolderTooLargeException(maxScannedFiles);
      }
      const relative = path
        .relative(directoryPath, absolute)
        .split(path.sep)
        .join("/");
      const stat = await fs.stat(absolute);
      const digest = await sha256OfFile(absolute);
      entries.push({
        relativePath: relative,
        absolutePath: absolute,
        sizeBytes: stat.size,
        sha256: digest,
      });
    }
  }

  await walk(directoryPath);
  entries.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
  return { name: path.basename(directoryPath), entries };
}
