import { createHash } from "node:crypto";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";

import { scanDirectory } from "../src/main/folder-scan.js";
import {
  FolderTooLargeException,
  MAX_SCANNED_FILES,
} from "../src/shared/folder-scan.js";

async function withTempDir(run: (dir: string) => Promise<void>): Promise<void> {
  const dir = await mkdtemp(path.join(os.tmpdir(), "folder-scan-"));
  try {
    await run(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

/** Injected cap for UG-10 limit tests — avoids creating 5001 files on slow Windows CI. */
const TEST_SCANNED_FILE_CAP = 10;

describe("folder scan (UG-10 / UG-11 / UG-12)", () => {
  it("UG-10: skips hidden files, OS metadata, and enforces the file cap", async () => {
    await withTempDir(async (dir) => {
      await writeFile(path.join(dir, ".hidden"), "secret");
      await writeFile(path.join(dir, "Thumbs.db"), "meta");
      await writeFile(path.join(dir, "visible.txt"), "ok");

      const folder = await scanDirectory(dir);
      expect(folder.entries).toHaveLength(1);
      expect(folder.entries[0]?.relativePath).toBe("visible.txt");
    });

    await withTempDir(async (dir) => {
      for (let index = 0; index < TEST_SCANNED_FILE_CAP + 1; index += 1) {
        await writeFile(path.join(dir, `file-${index}.txt`), "x");
      }
      await expect(
        scanDirectory(dir, { maxScannedFiles: TEST_SCANNED_FILE_CAP }),
      ).rejects.toBeInstanceOf(FolderTooLargeException);
    });
  });

  it("UG-10: production cap remains 5000 files", () => {
    expect(MAX_SCANNED_FILES).toBe(5000);
  });

  it("UG-11: normalizes Windows-style relative paths to forward slashes", async () => {
    await withTempDir(async (dir) => {
      const nested = path.join(dir, "subject-a");
      await mkdir(nested, { recursive: true });
      await writeFile(path.join(nested, "01_answers.pdf"), "%PDF");

      const folder = await scanDirectory(dir);
      expect(folder.entries[0]?.relativePath).toBe("subject-a/01_answers.pdf");
      expect(folder.entries[0]?.relativePath.includes("\\")).toBe(false);
    });
  });

  it("UG-12: returns only digests, never file contents", async () => {
    await withTempDir(async (dir) => {
      const content = "synthetic answer bytes";
      const filePath = path.join(dir, "01_answers.pdf");
      await writeFile(filePath, content);

      const folder = await scanDirectory(dir);
      const entry = folder.entries[0];
      expect(entry).toBeDefined();
      const expected = createHash("sha256").update(content).digest("hex");
      expect(entry?.sha256).toBe(expected);
      expect(JSON.stringify(folder)).not.toContain(content);
    });
  });
});
