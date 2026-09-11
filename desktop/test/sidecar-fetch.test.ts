import * as http from "node:http";
import type { AddressInfo } from "node:net";
import { inspect } from "node:util";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockIsPackaged = vi.hoisted(() => ({ value: false }));

vi.mock("electron", () => ({
  app: {
    get isPackaged() {
      return mockIsPackaged.value;
    },
  },
}));

import {
  SidecarTransportError,
  sidecarFetch,
} from "../src/main/sidecar-fetch.js";
import { UnsafeSidecarConnectionError } from "../src/main/sidecar-connection.js";

/**
 * A stand-in for the Python sidecar's auth semantics: `/healthz` is
 * unauthenticated, every other route needs the session token. Real HTTP over
 * loopback, so `sidecarFetch` builds the URL, attaches the header, and reads
 * the status the way it does in production.
 */
const GOOD_TOKEN = "the-session-token";

interface FakeSidecar {
  readonly host: string;
  readonly port: number;
  close(): Promise<void>;
}

async function startFakeSidecar(): Promise<FakeSidecar> {
  const server = http.createServer((request, response) => {
    const path = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
    if (path === "/healthz") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ status: "ok" }));
      return;
    }
    if (request.headers["authorization"] === `Bearer ${GOOD_TOKEN}`) {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: true }));
      return;
    }
    response.writeHead(401, { "content-type": "application/json" });
    response.end(JSON.stringify({ detail: "unauthorized" }));
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as AddressInfo;
  return {
    host: "127.0.0.1",
    port: address.port,
    close: () =>
      new Promise<void>((resolve, reject) =>
        server.close((error) =>
          error === undefined ? resolve() : reject(error),
        ),
      ),
  };
}

describe("sidecarFetch", () => {
  const running: FakeSidecar[] = [];

  beforeEach(() => {
    mockIsPackaged.value = false;
    delete process.env["AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT"];
    delete process.env["AUTO_SCORING_E2E_STUB_GRADING_JOBS"];
    delete process.env["AUTO_SCORING_E2E_STUB_BULK_EXPORT"];
  });

  afterEach(async () => {
    vi.unstubAllGlobals();
    delete process.env["AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT"];
    delete process.env["AUTO_SCORING_E2E_STUB_GRADING_JOBS"];
    delete process.env["AUTO_SCORING_E2E_STUB_BULK_EXPORT"];
    await Promise.all(running.map((sidecar) => sidecar.close()));
    running.length = 0;
  });

  async function fakeSidecar(): Promise<FakeSidecar> {
    const sidecar = await startFakeSidecar();
    running.push(sidecar);
    return sidecar;
  }

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

  it("INV-200: /healthz succeeds even though the token is bogus", async () => {
    const sidecar = await fakeSidecar();

    const response = await sidecarFetch(
      { host: sidecar.host, port: sidecar.port, token: "bogus-token" },
      { method: "GET", urlPath: "/healthz" },
    );

    expect(response.status).toBe(200);
  });

  it("INV-201: a protected path succeeds with the session token", async () => {
    const sidecar = await fakeSidecar();

    const response = await sidecarFetch(
      { host: sidecar.host, port: sidecar.port, token: GOOD_TOKEN },
      { method: "GET", urlPath: "/tests" },
    );

    expect(response.status).toBe(200);
    expect(
      JSON.parse(Buffer.from(response.bodyBase64, "base64").toString("utf8")),
    ).toEqual({ ok: true });
  });

  it("INV-202: a protected path answers 401 with the wrong token", async () => {
    const sidecar = await fakeSidecar();

    const response = await sidecarFetch(
      { host: sidecar.host, port: sidecar.port, token: "not-the-token" },
      { method: "GET", urlPath: "/tests" },
    );

    expect(response.status).toBe(401);
  });

  it("INV-203: rejects a non-loopback host before any request is sent", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const secret = "must-not-escape-token";

    let caught: unknown;
    try {
      await sidecarFetch(
        { host: "collector.example", port: 54321, token: secret },
        { method: "GET", urlPath: "/tests" },
      );
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(UnsafeSidecarConnectionError);
    expect(fetchSpy).not.toHaveBeenCalled();
    const rendered = [
      String(caught),
      (caught as Error).stack ?? "",
      inspect(caught),
    ].join("\n");
    expect(rendered).not.toContain(secret);
    expect(rendered).not.toContain("collector.example");
    expect(rendered).not.toContain("54321");
  });

  it("stubs criteria extract in E2E without calling the sidecar (Issue #293)", async () => {
    process.env["AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT"] = "1";
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const response = await sidecarFetch(
      { host: "127.0.0.1", port: 1, token: "unused" },
      {
        method: "POST",
        urlPath: "/tests/t-e2e/criteria/extract",
      },
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(200);
    const body = JSON.parse(
      Buffer.from(response.bodyBase64, "base64").toString("utf8"),
    ) as { test_id: string; questions: { number: string }[] };
    expect(body.test_id).toBe("t-e2e");
    expect(body.questions[0]?.number).toBe("問1");
  });

  it("stubs grading jobs from running to succeeded in E2E (Issue #319)", async () => {
    process.env["AUTO_SCORING_E2E_STUB_GRADING_JOBS"] = "1";
    const jobs = [
      {
        id: "job-1",
        kind: "grading",
        submission_id: "sub-stub-319",
        question_id: "q-1",
        state: "failed",
        usable: false,
        attempts: 1,
        max_attempts: 3,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ];
    const fetchSpy = vi.fn(
      async () =>
        new Response(JSON.stringify(jobs), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    const connection = { host: "127.0.0.1", port: 1, token: "unused" };

    const reads = [] as { state: string; usable: boolean | null }[];
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const response = await sidecarFetch(connection, {
        method: "GET",
        urlPath: "/submissions/sub-stub-319/jobs",
      });
      reads.push(
        (
          JSON.parse(
            Buffer.from(response.bodyBase64, "base64").toString("utf8"),
          ) as { state: string; usable: boolean | null }[]
        )[0]!,
      );
    }

    expect(reads.slice(0, 4)).toHaveLength(4);
    for (const read of reads.slice(0, 4)) {
      expect(read).toMatchObject({ state: "running", usable: null });
    }
    expect(reads[4]).toMatchObject({ state: "succeeded", usable: true });
    expect(fetchSpy).toHaveBeenCalledTimes(5);
  });

  it("stubs bulk export and its file in E2E (Issue #345)", async () => {
    process.env["AUTO_SCORING_E2E_STUB_BULK_EXPORT"] = "1";
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const connection = { host: "127.0.0.1", port: 1, token: "unused" };

    const requested = await sidecarFetch(connection, {
      method: "POST",
      urlPath: "/tests/t-e2e/export",
      bodyBase64: Buffer.from(
        JSON.stringify({ submission_ids: ["sub-1", "sub-2"] }),
      ).toString("base64"),
    });
    const body = JSON.parse(
      Buffer.from(requested.bodyBase64, "base64").toString("utf8"),
    ) as {
      test_id: string;
      items: { submission_id: string; status: string }[];
    };
    expect(body.test_id).toBe("t-e2e");
    expect(body.items).toEqual([
      { submission_id: "sub-1", status: "reused", export: expect.anything() },
      { submission_id: "sub-2", status: "reused", export: expect.anything() },
    ]);

    const file = await sidecarFetch(connection, {
      method: "GET",
      urlPath: "/exports/e2e-export-sub-1/file",
    });
    expect(file.status).toBe(200);
    expect(Buffer.from(file.bodyBase64, "base64").toString("utf8")).toContain(
      "%PDF-1.4",
    );
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("INV-204: a transport failure never echoes the URL, port, or token", async () => {
    const secret = "must-not-escape-token";
    const leaked = `connect ECONNREFUSED http://127.0.0.1:54321 token=${secret}`;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error(leaked);
      }),
    );

    let caught: unknown;
    try {
      await sidecarFetch(
        { host: "127.0.0.1", port: 54321, token: secret },
        { method: "GET", urlPath: "/tests" },
      );
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(SidecarTransportError);
    const rendered = [
      String(caught),
      (caught as Error).stack ?? "",
      inspect(caught),
    ].join("\n");
    expect(rendered).not.toContain(secret);
    expect(rendered).not.toContain("54321");
    expect(rendered).not.toContain("http://127.0.0.1");
  });
});
