import { afterEach, describe, expect, it, vi } from "vitest";

import { sidecarFetch } from "../src/main/sidecar-fetch.js";

describe("sidecarFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("attaches Authorization in main and returns base64 bodies", async () => {
    const pngBytes = Uint8Array.from([
      137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13,
    ]);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        const headers = new Headers(init?.headers);
        expect(headers.get("Authorization")).toBe("Bearer test-token");
        return new Response(pngBytes, {
          status: 200,
          statusText: "OK",
          headers: { "content-type": "image/png" },
        });
      }),
    );

    const response = await sidecarFetch(
      { host: "127.0.0.1", port: 43649, token: "test-token" },
      { method: "GET", urlPath: "/tests/t1/pages/0/image?scale=1" },
    );

    expect(response.status).toBe(200);
    expect(response.headers["content-type"]).toBe("image/png");
    expect(Buffer.from(response.bodyBase64, "base64")).toEqual(
      Buffer.from(pngBytes),
    );
  });
});
