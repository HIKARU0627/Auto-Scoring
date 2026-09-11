import { describe, expect, it } from "vitest";

import { toPublicSidecarStatus } from "../src/main/sidecar-connection.js";

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
