import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/** INV-003: async state updates must go through mounted guard, not bare setState. */
describe("PdfReviewPage mounted guard (INV-003)", () => {
  it("uses setStateIfMounted instead of unguarded async setState", () => {
    const file = resolve(
      import.meta.dirname,
      "../src/renderer/features/pdf-review/PdfReviewPage.tsx",
    );
    const source = readFileSync(file, "utf8");
    expect(source).toContain("setStateIfMounted");
    expect(source).toContain("useMountedRef");
    expect(source).not.toMatch(/await[\s\S]{0,200}\n\s+setLoadState\(/);
  });
});
