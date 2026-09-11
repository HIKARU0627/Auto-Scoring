import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, type Dirent } from "node:fs";
import * as path from "node:path";

/**
 * Take-over registry for Issue #322's 14 common-infrastructure invariants.
 *
 * §17.4 of `docs/frontend-invariants.md` still marks these as 未引き取り
 * because the §18 classification (A: structurally impossible, B: covered by
 * another test) was only prose. This Issue claims them by making the
 * guarantees executable; this file is the index that keeps the claim honest.
 *
 * For every ID it requires at least one test file (other than this one) to name
 * the ID. Deleting the last test for an invariant, or writing the ID in the
 * markdown only, turns this red. The count is fixed at 14 so an ID silently
 * dropped from the list cannot make it pass.
 *
 * This is a registry, not the behavioural proof: the red-on-break test for each
 * ID lives in the file the scan reports.
 */

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const TEST_DIR = path.join(PACKAGE_ROOT, "test");
const SELF = path.basename(import.meta.filename);

/** The 14 IDs assigned to Issue #322 (Issue body, §17.4 rows). */
const CLAIMED_IDS = [
  "INV-010",
  "INV-011",
  "INV-020",
  "INV-091",
  "INV-092",
  "INV-095",
  "UG-02",
  "UG-03",
  "UG-04",
  "INV-201-04",
  "INV-100",
  "INV-102",
  "INV-201-07",
  "UG-13",
] as const;

const EXPECTED_CLAIMED_COUNT = 14;

function testFilesUnder(dir: string): string[] {
  const found: string[] = [];
  let entries: Dirent[];
  try {
    entries = readdirSync(dir, { withFileTypes: true, recursive: true });
  } catch {
    return [];
  }
  for (const entry of entries) {
    if (
      !entry.isFile() ||
      entry.name === SELF ||
      !/\.test\.tsx?$/.test(entry.name)
    ) {
      continue;
    }
    found.push(path.join(entry.parentPath, entry.name));
  }
  return found.sort();
}

function filesNaming(id: string): string[] {
  const pattern = new RegExp(`\\b${id}\\b`);
  return testFilesUnder(TEST_DIR)
    .filter((file) => pattern.test(readFileSync(file, "utf8")))
    .map((file) => path.relative(PACKAGE_ROOT, file));
}

describe("Issue #322 common-infrastructure invariants are claimed (14 件)", () => {
  it("the list itself is the fixed 14", () => {
    expect(CLAIMED_IDS).toHaveLength(EXPECTED_CLAIMED_COUNT);
    expect(new Set(CLAIMED_IDS).size).toBe(CLAIMED_IDS.length);
  });

  for (const id of CLAIMED_IDS) {
    it(`${id} is named by a test`, () => {
      const files = filesNaming(id);
      expect(
        files,
        `${id} を名指すテストが desktop/test に無い（docs に書いただけでは赤のまま）`,
      ).not.toEqual([]);
    });
  }
});
