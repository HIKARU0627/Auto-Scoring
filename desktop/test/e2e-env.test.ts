import { describe, expect, it } from "vitest";

import { readE2eEnv } from "../src/main/e2e-env.js";

describe("readE2eEnv (UG-05)", () => {
  it("ignores E2E overrides when the app is packaged", () => {
    const env = {
      AUTO_SCORING_E2E_FOLDER: "/tmp/e2e-folder",
      AUTO_SCORING_E2E_PDF: "/tmp/e2e.pdf",
      AUTO_SCORING_E2E_APP_DATA: "/tmp/e2e-app-data",
    };

    expect(readE2eEnv("AUTO_SCORING_E2E_FOLDER", true, env)).toBeUndefined();
    expect(readE2eEnv("AUTO_SCORING_E2E_PDF", true, env)).toBeUndefined();
    expect(readE2eEnv("AUTO_SCORING_E2E_APP_DATA", true, env)).toBeUndefined();
  });

  it("returns non-empty values only for unpackaged builds", () => {
    const env = {
      AUTO_SCORING_E2E_FOLDER: "/tmp/e2e-folder",
      AUTO_SCORING_E2E_PDF: "",
    };

    expect(readE2eEnv("AUTO_SCORING_E2E_FOLDER", false, env)).toBe(
      "/tmp/e2e-folder",
    );
    expect(readE2eEnv("AUTO_SCORING_E2E_PDF", false, env)).toBeUndefined();
    expect(readE2eEnv("AUTO_SCORING_E2E_MISSING", false, env)).toBeUndefined();
  });
});
