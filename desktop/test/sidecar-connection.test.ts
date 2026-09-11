import { inspect } from "node:util";
import { describe, expect, it } from "vitest";

import {
  assertLoopbackConnection,
  isLoopbackHost,
  toPublicSidecarStatus,
  UnsafeSidecarConnectionError,
} from "../src/main/sidecar-connection.js";

describe("toPublicSidecarStatus", () => {
  it("strips the bearer token from ready status (Issue #264)", () => {
    const publicStatus = toPublicSidecarStatus({
      kind: "ready",
      connection: {
        host: "127.0.0.1",
        port: 43649,
        token: "super-secret-token",
      },
    });

    expect(publicStatus).toEqual({
      kind: "ready",
      connection: { host: "127.0.0.1", port: 43649 },
    });
    expect(JSON.stringify(publicStatus)).not.toContain("super-secret-token");
  });
});

describe("isLoopbackHost", () => {
  it("accepts the loopback literal the sidecar binds", () => {
    expect(isLoopbackHost("127.0.0.1")).toBe(true);
  });

  it("rejects every non-loopback destination", () => {
    for (const host of [
      "0.0.0.0",
      "localhost",
      "127.0.0.2",
      "192.168.1.10",
      "example.test",
      "::1",
      "evil.example",
    ]) {
      expect(isLoopbackHost(host)).toBe(false);
    }
  });
});

describe("assertLoopbackConnection (INV-203)", () => {
  it("accepts a loopback connection", () => {
    expect(() =>
      assertLoopbackConnection({
        host: "127.0.0.1",
        port: 43649,
        token: "session-token",
      }),
    ).not.toThrow();
  });

  it("rejects a non-loopback host without echoing the URL or token", () => {
    const secret = "must-not-escape-token";
    const host = "collector.example";

    let caught: unknown;
    try {
      assertLoopbackConnection({ host, port: 54321, token: secret });
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(UnsafeSidecarConnectionError);
    // The whole rendered error, not just `.message`: a stack or an inspected
    // object is what actually reaches a log file.
    const rendered = [
      String(caught),
      (caught as Error).stack ?? "",
      inspect(caught),
    ].join("\n");
    expect(rendered).not.toContain(secret);
    expect(rendered).not.toContain(host);
    expect(rendered).not.toContain("54321");
  });
});
