import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import * as path from "node:path";

/**
 * Issue #384 (3): the intake session lives only in module memory.
 *
 * Persisting it to `localStorage`/`sessionStorage`/IndexedDB would survive a
 * restart, and a folder whose contents changed would then show a selection
 * that no longer matches the files. The coordinator ruled that out, so the two
 * files that own the session must not reach for any storage API.
 */
const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const SESSION_FILES = [
  "src/renderer/core/intake-data.ts",
  "src/renderer/features/intake/IntakePage.tsx",
];

describe("Issue #384 (3): the intake session is not persisted", () => {
  it("neither session file touches a disk storage API", () => {
    const hits = SESSION_FILES.filter((file) => {
      const source = readFileSync(path.join(PACKAGE_ROOT, file), "utf8");
      return /localStorage|sessionStorage|indexedDB/.test(source);
    });
    expect(hits).toEqual([]);
  });
});
