/**
 * Folder scan contract shared between the main process and the renderer.
 *
 * The scan walks a chosen directory, hashes each file, and returns only
 * metadata — no file content crosses IPC (UG-12).
 */

/** One file found under the chosen folder. */
export interface ScannedEntry {
  /** POSIX-separated path relative to the chosen folder (UG-11). */
  readonly relativePath: string;
  /** Absolute path on disk — used only by the main process for uploads. */
  readonly absolutePath: string;
  readonly sizeBytes: number;
  /** Content digest (sha256 hex). */
  readonly sha256: string;
}

/** A chosen folder and everything listed under it. */
export interface ScannedFolder {
  /** The folder's own name. */
  readonly name: string;
  readonly entries: readonly ScannedEntry[];
}

/** Files never worth listing (UG-10). */
export const IGNORED_FILE_NAMES = new Set([
  ".ds_store",
  "thumbs.db",
  "desktop.ini",
]);

/** Upper bound on how many files one scan will list (UG-10). */
export const MAX_SCANNED_FILES = 5000;

/** Optional overrides for folder scan (tests inject a smaller cap to avoid slow I/O). */
export interface ScanDirectoryOptions {
  readonly maxScannedFiles?: number;
}

/** Raised when the chosen folder holds more than [MAX_SCANNED_FILES] files. */
export class FolderTooLargeException extends Error {
  readonly found: number;

  constructor(found: number) {
    super(
      `このフォルダには${found}件以上のファイルがあります。` +
        "取り込む資料が入ったフォルダを選んでください。",
    );
    this.name = "FolderTooLargeException";
    this.found = found;
  }
}
