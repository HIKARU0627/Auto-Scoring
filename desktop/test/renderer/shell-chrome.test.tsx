import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  AppRoutes,
  declaredRoutePatterns,
} from "../../src/renderer/core/app-routes.js";
import {
  pageSubtitleFor,
  pageTitleFor,
} from "../../src/renderer/navigation/page-header.js";
import { SIDEBAR_PRODUCT_NAME } from "../../src/renderer/navigation/Sidebar.js";
import { ShellScreen } from "../../src/renderer/navigation/ShellScreen.js";
import { RouterProvider } from "../../src/renderer/navigation/router.js";

function fill(path: string): string {
  return path.replace(":testId", "test-1").replace(":submissionId", "sub-1");
}

function renderShellAt(location: string): void {
  render(
    <RouterProvider initialStack={[location]}>
      <ShellScreen />
    </RouterProvider>,
  );
}

/**
 * Issue #348 (parent #333): evaluation A saw the product name twice -- once in
 * the sidebar and again as the body heading. The shell now derives the screen
 * name when a screen supplies no title, and the header is separated from the
 * body by spacing rather than a full-width 1px rule that split the app in two.
 *
 * `features/` is owned by other in-flight issues, so `HomePage` still draws its
 * own product-name header; the PR hands that migration off. These tests pin the
 * shell side: the default is a screen name, never the product name, and the
 * header carries no rule.
 */
describe("shell page heading (Issue #348)", () => {
  it("derives the screen name when a screen supplies no title", () => {
    renderShellAt(AppRoutes.home);
    expect(screen.getByTestId("page-title").textContent).toBe("ホーム");
  });

  it("never falls back to the product name the sidebar already shows", () => {
    // `/starting` is not a screen (a startup placeholder), so it has no chrome.
    const screens = declaredRoutePatterns.filter(
      (pattern) => pattern !== AppRoutes.starting,
    );
    for (const pattern of screens) {
      const location = fill(pattern);
      const title = pageTitleFor(location);
      expect(title, `${location} has no derived heading`).not.toBeNull();
      expect(title).not.toBe(SIDEBAR_PRODUCT_NAME);
    }
  });

  it("keeps the route's subtitle under the derived heading", () => {
    expect(pageSubtitleFor(AppRoutes.home)).toBe("今日もよい添削を");
  });

  it("separates the header from the body with spacing, not a horizontal rule", () => {
    renderShellAt(AppRoutes.intake);
    const header = screen.getByTestId("page-title").closest("header");
    expect(header).not.toBeNull();
    const borderClasses = Array.from(header?.classList ?? []).filter((token) =>
      token.startsWith("border"),
    );
    expect(borderClasses).toEqual([]);
  });
});
