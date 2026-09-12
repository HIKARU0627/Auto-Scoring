import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";

/**
 * Issue #398: the banner is mounted at the router top (`AppShell`), so it is
 * asked once per connection and sits above whatever screen is shown -- not
 * only home, and not re-implemented per screen (INV-168).
 */
describe("AppShell grading-unavailable banner (INV-168, Issue #398)", () => {
  it("shows the band above home when the sidecar says grading is unavailable", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        getGradingAvailability: async () => ({
          available: false,
          reason: "AUTO_SCORING_AI_GRADING_TRANSPORT is not set",
        }),
      },
    });

    expect(
      await screen.findByTestId("grading-unavailable-banner"),
    ).toBeDefined();
    expect(screen.getByTestId("grading-unavailable-headline")).toBeDefined();
    expect(screen.getByTestId("grading-unavailable-reason").textContent).toBe(
      "AUTO_SCORING_AI_GRADING_TRANSPORT is not set",
    );
    // The band stacks over the screen; it does not replace it.
    expect(screen.getByTestId("home-open-intake")).toBeDefined();
    // Issue #375 item 4: the shell frame is content-height, so the band must
    // not force the window height back on either.
    expect(
      screen.getByTestId("grading-unavailable-banner").parentElement
        ?.className ?? "",
    ).not.toContain("min-h-screen");
  });

  it("stays above a pushed screen, not only home", async () => {
    renderAppAt(AppRoutes.settings, {
      handlers: {
        getGradingAvailability: async () => ({ available: false }),
      },
    });

    expect(
      await screen.findByTestId("grading-unavailable-banner"),
    ).toBeDefined();
    expect(screen.getByTestId("settings-tab-intake")).toBeDefined();
  });

  it("shows no band when the sidecar says grading is available", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        getGradingAvailability: async () => ({ available: true }),
      },
    });

    expect(await screen.findByTestId("home-open-intake")).toBeDefined();
    await waitFor(() => {
      expect(screen.queryByTestId("grading-unavailable-banner")).toBeNull();
    });
  });

  it("shows no band while the sidecar has not answered (null)", async () => {
    renderAppAt(AppRoutes.home, {
      handlers: {
        getGradingAvailability: async () => {
          throw new Error("sidecar not reachable");
        },
      },
    });

    expect(await screen.findByTestId("home-open-intake")).toBeDefined();
    expect(screen.queryByTestId("grading-unavailable-banner")).toBeNull();
  });
});
