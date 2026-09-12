import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";

/**
 * Issue #427: the sidebar is fixed, not a column that rides the screen down.
 *
 * `position: sticky` on the Sidebar never held by itself: sticky is clamped to
 * its containing block, and the shell frame's box ends at the viewport while a
 * tall screen's content overflows it, so the panel had nothing left to stick to
 * and scrolled away with the document. The fix is structural -- the frame keeps
 * a definite height and the body column caps to it (`max-h-full`) and owns the
 * scroll (`overflow-y-auto`), so the document (and with it the panel and the
 * banner) never moves.
 *
 * jsdom has no layout, so this pins the class contract the fix rests on;
 * `desktop/e2e/sidebar-fixed.spec.ts` fixes the pixels in all four
 * banner x content-height states.
 */
describe("sidebar stays put while the screen scrolls (Issue #427)", () => {
  function renderHome(available: boolean): void {
    renderAppAt(AppRoutes.home, {
      handlers: {
        getGradingAvailability: async () => ({ available }),
      },
    });
  }

  function expectBodyColumnOwnsTheScroll(): void {
    const sidebar = screen.getByTestId("app-sidebar");
    const frame = sidebar.parentElement as HTMLElement;
    const content = screen.getByTestId("app-shell-content");

    // The frame stays a definite-height row; the body column, not the window,
    // is what scrolls.
    expect(frame.className).toContain("items-start");
    expect(content.className).toContain("max-h-full");
    expect(content.className).toContain("min-h-0");
    expect(content.className).toContain("overflow-y-auto");

    // The panel stretches to that frame and is never a literal viewport column;
    // it is not the element that scrolls.
    expect(sidebar.className).toContain("self-stretch");
    expect(sidebar.className).not.toContain("h-screen");
    expect(sidebar.className).not.toContain("100vh");
    expect(sidebar.className).not.toContain("overflow-y-auto");
  }

  it("keeps the sidebar fixed while the body column scrolls", async () => {
    renderHome(true);
    await screen.findByTestId("home-open-intake");
    expectBodyColumnOwnsTheScroll();
  });

  it("keeps the body column as the only scroller with the banner up too", async () => {
    renderHome(false);
    await screen.findByTestId("grading-unavailable-banner");
    await screen.findByTestId("home-open-intake");
    expectBodyColumnOwnsTheScroll();
  });
});
