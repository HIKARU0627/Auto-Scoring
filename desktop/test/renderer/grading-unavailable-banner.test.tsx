import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { GradingUnavailableBanner } from "../../src/renderer/core/GradingUnavailableBanner.js";

/**
 * INV-168: the banner is shown **only** when the sidecar has answered that
 * grading is unavailable. "No answer yet" (`null`) is not "cannot grade"; a
 * single failed request must not turn into a configuration accusation.
 */
function renderBanner(
  availability: Parameters<typeof GradingUnavailableBanner>[0]["availability"],
) {
  return render(
    <GradingUnavailableBanner availability={availability}>
      <div>画面の中身</div>
    </GradingUnavailableBanner>,
  );
}

describe("GradingUnavailableBanner (INV-168)", () => {
  it("shows the banner and the reason when grading is unavailable", () => {
    renderBanner({
      available: false,
      reason: "AUTO_SCORING_AI_GRADING_TRANSPORT is required",
    });

    expect(screen.getByTestId("grading-unavailable-headline")).toBeDefined();
    expect(screen.getByTestId("grading-unavailable-reason").textContent).toBe(
      "AUTO_SCORING_AI_GRADING_TRANSPORT is required",
    );
    // The banner does not hide the screen underneath.
    expect(screen.getByText("画面の中身")).toBeDefined();
  });

  it("shows the banner even when there is no reason", () => {
    renderBanner({ available: false });

    expect(screen.getByTestId("grading-unavailable-headline")).toBeDefined();
    expect(screen.queryByTestId("grading-unavailable-reason")).toBeNull();
  });

  it("shows nothing when grading is available", () => {
    renderBanner({ available: true });

    expect(screen.queryByTestId("grading-unavailable-headline")).toBeNull();
    expect(screen.getByText("画面の中身")).toBeDefined();
  });

  it("shows nothing while the sidecar has not answered (null)", () => {
    renderBanner(null);

    expect(screen.queryByTestId("grading-unavailable-headline")).toBeNull();
    expect(screen.getByText("画面の中身")).toBeDefined();
  });
});
