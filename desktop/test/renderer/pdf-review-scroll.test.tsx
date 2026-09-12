import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { resolveWorkspaceHeight } from "../../src/renderer/features/pdf-review/PdfReviewPage.js";
import {
  buildQuestion,
  renderPdfReview,
} from "./support/pdf-review-harness.js";

const WAIT_MS = 5000;

/**
 * Issue #401: the answer PDF must be the only thing that scrolls, with the
 * 設問レール and 採点パネル held on screen.
 *
 * jsdom has no layout, so the actual scrolling is fixed by the real-app spec
 * `desktop/e2e/sidecar-review-scroll.spec.ts`. What these tests pin down is the
 * contract the layout depends on: the viewport fit arithmetic, and the fact
 * that both the rail and the page region are given their own bounded scroll
 * container instead of growing the page.
 */
describe("review workspace is fitted to the viewport (Issue #401)", () => {
  it("subtracts the workspace's own top and the bottom inset from the viewport", () => {
    expect(
      resolveWorkspaceHeight({
        viewportHeight: 1024,
        workspaceTop: 323,
        sideBySide: true,
      }),
    ).toBe(653);
  });

  it("leaves the height unset when the panes stack", () => {
    expect(
      resolveWorkspaceHeight({
        viewportHeight: 1024,
        workspaceTop: 323,
        sideBySide: false,
      }),
    ).toBeNull();
  });

  it("leaves the height unset when the viewport is already spent", () => {
    expect(
      resolveWorkspaceHeight({
        viewportHeight: 371,
        workspaceTop: 323,
        sideBySide: true,
      }),
    ).toBeNull();
  });

  it("gives the 設問レール its own bounded scroll container", async () => {
    renderPdfReview({
      questions: Array.from({ length: 8 }, (_, index) =>
        buildQuestion({ id: `q-${index + 1}`, number: `${index + 1}` }),
      ),
      grades: [],
    });

    await waitFor(
      () => {
        expect(screen.getByTestId("review-rail-q-8")).toBeDefined();
      },
      { timeout: WAIT_MS },
    );

    const rail = screen.getByTestId("review-question-rail").className;
    expect(rail).toContain("overflow-y-auto");
    expect(rail).toContain("max-h-inspector");
  });

  it("lets the page region scroll on both axes inside the workspace", async () => {
    renderPdfReview({ grades: [] });

    await waitFor(
      () => {
        expect(screen.getByTestId("review-page-region")).toBeDefined();
      },
      { timeout: WAIT_MS },
    );

    const region = screen.getByTestId("review-page-region").className;
    expect(region).toContain("overflow-auto");
    expect(region).toContain("max-h-inspector");
    // `overflow-x-auto` alone left the zoomed page's vertical growth to push
    // the whole document (the Issue #401 bug).
    expect(region).not.toContain("overflow-x-auto");
  });
});
