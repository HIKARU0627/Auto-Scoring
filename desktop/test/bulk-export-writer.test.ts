import { describe, expect, it } from "vitest";

import {
  createMemoryBulkExportStorage,
  createPathBulkExportStorage,
  resolveFreeExportPath,
  writeBulkExportFile,
  type BulkExportPathBridge,
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

  it("writing the same name three times yields x.pdf, x_2.pdf, x_3.pdf (UG-09)", async () => {
    // 上書きしないことを否定形 (既存が消えない) だけで書くと、書き出し
    // そのものが動かなくても緑のままになる。3回書いて3つとも残ることを
    // 肯定形で固定する (docs/frontend-invariants.md §14.2 UG-09 の指示)。
    const storage = createMemoryBulkExportStorage();
    const first = new Uint8Array([1]);
    const second = new Uint8Array([2]);
    const third = new Uint8Array([3]);

    expect(
      await writeBulkExportFile(storage, "answer_corrected.pdf", first),
    ).toBe("answer_corrected.pdf");
    expect(
      await writeBulkExportFile(storage, "answer_corrected.pdf", second),
    ).toBe("answer_corrected_2.pdf");
    expect(
      await writeBulkExportFile(storage, "answer_corrected.pdf", third),
    ).toBe("answer_corrected_3.pdf");

    expect(await storage.read("answer_corrected.pdf")).toEqual(first);
    expect(await storage.read("answer_corrected_2.pdf")).toEqual(second);
    expect(await storage.read("answer_corrected_3.pdf")).toEqual(third);
  });
});

describe("path-backed bulk-export storage (Issue #345)", () => {
  function bridgeSpy(): BulkExportPathBridge & {
    written: { directoryPath: string; fileName: string; bytesBase64: string }[];
  } {
    const written: {
      directoryPath: string;
      fileName: string;
      bytesBase64: string;
    }[] = [];
    return {
      written,
      bulkExportFileExists: async () => false,
      bulkExportReadFile: async () => null,
      bulkExportWriteFile: async (request) => {
        written.push(request);
        return request.fileName;
      },
    };
  }

  it("round-trips bytes through the main-process bridge as base64", async () => {
    const bridge = bridgeSpy();
    const storage = createPathBulkExportStorage("/chosen/out", bridge);
    const bytes = new Uint8Array([0, 1, 2, 253, 254, 255]);

    const savedName = await writeBulkExportFile(
      storage,
      "answer_corrected.pdf",
      bytes,
    );

    expect(savedName).toBe("answer_corrected.pdf");
    expect(bridge.written).toHaveLength(1);
    expect(bridge.written[0]?.directoryPath).toBe("/chosen/out");
    expect(bridge.written[0]?.fileName).toBe("answer_corrected.pdf");
    expect(
      Uint8Array.from(atob(bridge.written[0]!.bytesBase64), (character) =>
        character.charCodeAt(0),
      ),
    ).toEqual(bytes);
  });

  it("returns the name main chose so a suffixed file is reported", async () => {
    const bridge: BulkExportPathBridge = {
      bulkExportFileExists: async () => false,
      bulkExportReadFile: async () => null,
      bulkExportWriteFile: async () => "answer_corrected_2.pdf",
    };
    const storage = createPathBulkExportStorage("/chosen/out", bridge);

    const savedName = await writeBulkExportFile(
      storage,
      "answer_corrected.pdf",
      new Uint8Array([1]),
    );

    expect(savedName).toBe("answer_corrected_2.pdf");
  });
});
