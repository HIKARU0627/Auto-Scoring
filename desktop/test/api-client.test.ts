import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import * as path from "node:path";

import { createSidecarClient } from "../src/renderer/api/client.js";

/**
 * Issue #228: the generated schema must cover the page image / geometry
 * endpoints from Issue #207, and the thin client must stay free of coordinate
 * conversion helpers that divide by geometry dimensions.
 */

const GENERATED_SCHEMA = path.resolve(
  import.meta.dirname,
  "../src/renderer/api/generated/schema.ts",
);

const PAGE_ENDPOINT_PATHS = [
  "/submissions/{submission_id}/pages",
  "/submissions/{submission_id}/pages/{page_index}/image",
  "/tests/{test_id}/answer-layout/pages",
  "/tests/{test_id}/answer-layout/pages/{page_index}/image",
] as const;

describe("generated OpenAPI schema", () => {
  it("includes the four page image / geometry endpoints", () => {
    const source = readFileSync(GENERATED_SCHEMA, "utf8");
    for (const route of PAGE_ENDPOINT_PATHS) {
      expect(source).toContain(`"${route}"`);
    }
    expect(source).toContain("PageGeometryResponse");
  });
});

describe("createSidecarClient", () => {
  it("returns a typed client without coordinate-conversion helpers", () => {
    const client = createSidecarClient({
      host: "127.0.0.1",
      port: 12345,
    });

    // The wrapper only exposes the fetch client; no geometry-based normalizers.
    expect(typeof client.GET).toBe("function");
    expect(typeof client.POST).toBe("function");
    expect(client).not.toHaveProperty("normalize");
    expect(client).not.toHaveProperty("toNormalized");
    expect(client).not.toHaveProperty("fromGeometry");
  });
});
