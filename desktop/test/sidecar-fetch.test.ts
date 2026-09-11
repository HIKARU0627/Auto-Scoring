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
  });

  afterEach(async () => {
    vi.unstubAllGlobals();
    delete process.env["AUTO_SCORING_E2E_STUB_CRITERIA_EXTRACT"];
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
