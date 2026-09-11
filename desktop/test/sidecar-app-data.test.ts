import { describe, expect, it } from "vitest";

import { resolveSidecarAppDataDirectory } from "../src/main/sidecar-app-data.js";

describe("resolveSidecarAppDataDirectory", () => {
  it("returns null when packaged even if AUTO_SCORING_E2E_APP_DATA is set (UG-05)", () => {
    expect(
      resolveSidecarAppDataDirectory({
        isPackaged: true,
        env: { AUTO_SCORING_E2E_APP_DATA: "/tmp/evil" },
      }),
    ).toBeNull();
  });

  it("returns the env path when not packaged (E2E harness only)", () => {
    expect(
      resolveSidecarAppDataDirectory({
        isPackaged: false,
        env: { AUTO_SCORING_E2E_APP_DATA: "/tmp/e2e-app-data" },
      }),
    ).toBe("/tmp/e2e-app-data");
  });

  it("returns null when not packaged and env is unset (UG-06 default)", () => {
    expect(
      resolveSidecarAppDataDirectory({
        isPackaged: false,
        env: {},
      }),
    ).toBeNull();
  });
});
