import { describe, expect, it } from "vitest";

import {
  createMemoryBulkExportStorage,
  resolveFreeExportPath,
  writeBulkExportFile,
} from "../src/renderer/core/bulk-export-writer.js";

describe("bulk-export-writer (UG-09)", () => {
  it("never overwrites an existing file — uses _2, _3 instead", async () => {
    const original = new Uint8Array([9, 9, 9]);
    const storage = createMemoryBulkExportStorage({
      "answer_corrected.pdf": original,
    });

    const writtenName = await writeBulkExportFile(
      storage,
      "answer_corrected.pdf",
      new Uint8Array([1, 2, 3]),
    );

    expect(writtenName).toBe("answer_corrected_2.pdf");
    expect(await storage.read("answer_corrected.pdf")).toEqual(original);
    expect(await storage.read("answer_corrected_2.pdf")).toEqual(
      new Uint8Array([1, 2, 3]),
    );
  });

  it("keeps incrementing until a free name is found", async () => {
    const storage = createMemoryBulkExportStorage({
      "answer_corrected.pdf": new Uint8Array([1]),
      "answer_corrected_2.pdf": new Uint8Array([2]),
    });

    const writtenName = await resolveFreeExportPath(
      "answer_corrected.pdf",
      (name) => storage.exists(name),
    );

    expect(writtenName).toBe("answer_corrected_3.pdf");
  });
});
