import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, type Dirent } from "node:fs";
import * as path from "node:path";

/**
 * INV-201-07: 廃止した文言が二度と現れない
 * (`docs/frontend-invariants.md` §1, §8; Issue #322).
 *
 * Home once asked for a "模範解答 PDF", the old name "採点マニュアル PDF" stuck
 * around, and the intake screen punted with "画面はまだありません". This is the
 * app-wide regression guard: the screening tests on individual screens
 * (`home-page.test.tsx`, `intake-page.test.tsx`) catch a bare "模範解答" on the
 * screens where it used to appear, while this scan catches the named, retired
 * strings anywhere in the renderer.
 *
 * The scan is deliberately narrower than the screen tests: "模範解答" alone is a
 * legitimate region label (`region-helpers.ts`) and material wording
 * (`dag-failure-guidance.ts`), so only the retired names are forbidden here.
 */

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const RENDERER_DIR = path.join(PACKAGE_ROOT, "src/renderer");
const SOURCE_EXTENSIONS = new Set([".ts", ".tsx"]);

/** The exact names that were retired; bare "模範解答" is not on this list. */
const RETIRED_COPY: readonly {
  readonly label: string;
  readonly pattern: RegExp;
}[] = [
  { label: "模範解答 PDF", pattern: /模範解答\s*PDF/g },
  { label: "採点マニュアル", pattern: /採点マニュアル/g },
  { label: "画面はまだありません", pattern: /画面はまだありません/g },
  // Issue #384: the owner did not know what a "バッチ" was. The intake screen
  // now names the folder it is importing, and this exact old heading is barred.
  {
    label: "このバッチはどのテストの答案ですか",
    pattern: /このバッチはどのテストの答案ですか/g,
  },
];

/** Lower bound so a renamed directory cannot make the scan pass on nothing. */
const EXPECTED_MIN_RENDERER_FILES = 80;

function sourceFilesUnder(dir: string): string[] {
  const found: string[] = [];
  let entries: Dirent[];
  try {
    entries = readdirSync(dir, { withFileTypes: true, recursive: true });
  } catch {
    return [];
  }
  for (const entry of entries) {
    if (!entry.isFile() || !SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      continue;
    }
    found.push(
      path
        .relative(PACKAGE_ROOT, path.join(entry.parentPath, entry.name))
        .split(path.sep)
        .join("/"),
    );
  }
  return found.sort();
}

function detectRetiredCopy(source: string): string[] {
  return RETIRED_COPY.flatMap(({ label, pattern }) => {
    pattern.lastIndex = 0;
    return pattern.test(source) ? [label] : [];
  });
}

describe("retired copy never returns (INV-201-07)", () => {
  it("scans at least the expected number of renderer files (prevents a vacuous pass)", () => {
    const files = sourceFilesUnder(RENDERER_DIR);
    expect(
      files.length,
      `Expected >= ${EXPECTED_MIN_RENDERER_FILES} renderer files to be scanned, found ${files.length}`,
    ).toBeGreaterThanOrEqual(EXPECTED_MIN_RENDERER_FILES);
  });

  it("the scanner recognises each retired name (positive control)", () => {
    expect(detectRetiredCopy("模範解答 PDF を提出してください")).toEqual([
      "模範解答 PDF",
    ]);
    expect(detectRetiredCopy("模範解答PDF")).toEqual(["模範解答 PDF"]);
    expect(detectRetiredCopy("採点マニュアル PDF")).toEqual(["採点マニュアル"]);
    expect(detectRetiredCopy("画面はまだありません")).toEqual([
      "画面はまだありません",
    ]);
    expect(detectRetiredCopy("このバッチはどのテストの答案ですか")).toEqual([
      "このバッチはどのテストの答案ですか",
    ]);
    // A legitimate bare region/material label is not a hit.
    expect(detectRetiredCopy('return "模範解答";')).toEqual([]);
  });

  it("no retired name appears anywhere under src/renderer", () => {
    const violations = sourceFilesUnder(RENDERER_DIR).flatMap((file) =>
      detectRetiredCopy(
        readFileSync(path.join(PACKAGE_ROOT, file), "utf8"),
      ).map((label) => `${file}: ${label}`),
    );
    expect(violations).toEqual([]);
  });
});
