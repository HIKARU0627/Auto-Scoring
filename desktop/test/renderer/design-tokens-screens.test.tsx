import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import { buildTest } from "./support/mock-sidecar-client.js";

/**
 * INV-081: Walks every major screen under both light and dark themes.
 *
 * Corresponds to Flutter `design_tokens_screens_test.dart:73`.
 * Verifies that each screen renders without unhandled exceptions under both
 * light and dark themes, and its root element derives its background from
 * the design token surface ramp (bg-surface).
 */

const defaultHandlers = {
  listTestRegistrations: async () => [
    buildTest({ id: "test-1", status: "draft" }),
  ],
  listSubmissions: async () => [],
};

const screens: Record<string, string> = {
  ホーム画面: AppRoutes.home,
  資料取込画面: AppRoutes.intake,
  テスト一覧画面: AppRoutes.testList,
  テスト設定画面: "/tests/test-1/settings",
  設定画面: AppRoutes.settings,
  答案一覧画面: "/tests/test-1/submissions",
  答案確定画面: "/tests/test-1/submissions/sub-1/confirm",
  添削レビュー画面: "/tests/test-1/submissions/sub-1/review",
};

describe("design tokens screens (INV-081)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
    delete document.documentElement.dataset["theme"];
  });

  for (const theme of ["light", "dark"] as const) {
    for (const [screenName, path] of Object.entries(screens)) {
      it(`${screenName} renders under ${theme} theme with background from token surface ramp`, async () => {
        localStorage.setItem("auto-scoring-theme", theme);

        const result = renderAppAt(path, { handlers: defaultHandlers });
        expect(result.container).toBeDefined();

        // Check document theme applied
        expect(document.documentElement.dataset["theme"]).toBe(theme);

        // Find the root element of the screen within the rendered shell
        // Screens render a container with min-h-screen and bg-surface
        const screenRoot =
          result.container.querySelector(".min-h-screen") ??
          result.container.firstElementChild;
        expect(
          screenRoot,
          `${screenName} must render a valid root container`,
        ).not.toBeNull();

        const classList = screenRoot!.className;
        // Background must be derived from token surface ramp (e.g. bg-surface or bg-surface-container*)
        const hasSurfaceBg = /\bbg-surface(?:-container(?:-[a-z]+)?)?\b/.test(
          classList,
        );
        expect(
          hasSurfaceBg,
          `${screenName} root background (${classList}) must derive from the theme surface ramp (bg-surface), not a hardcoded colour`,
        ).toBe(true);

        // Must not contain hard-coded background colour literals
        expect(classList).not.toMatch(/\bbg-(?:white|black)\b/);
        expect(classList).not.toMatch(/\bbg-\[[^\]]+\]/);
      });
    }
  }
});
