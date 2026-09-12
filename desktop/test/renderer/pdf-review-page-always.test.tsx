import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import {
  buildGrade,
  buildQuestion,
  renderPdfReview,
} from "./support/pdf-review-harness.js";

const WAIT_MS = 5000;

function waitForRegion(): HTMLElement {
  return screen.getByTestId("review-page-region");
}

describe("answer PDF is always visible (Issue #385)", () => {
  it("keeps the page region on screen when no question is selected", async () => {
    renderPdfReview({ questions: [], jobs: [], grades: [] });

    await waitFor(
      () => {
        expect(waitForRegion()).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    // The first page is shown even though the question rail is empty.
    expect(screen.getByTestId("review-page-surface")).toBeDefined();
    expect(screen.queryByTestId("review-page-unavailable")).toBeNull();
    expect(screen.getByTestId("review-page-indicator").textContent).toBe(
      "1 / 1",
    );
  });

  it("explains why the region is empty when the submission has no pages", async () => {
    renderPdfReview({ pages: [] });

    await waitFor(
      () => {
        expect(screen.getByTestId("review-page-unavailable")).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    expect(waitForRegion()).toBeDefined();
    expect(screen.getByTestId("review-page-unavailable").textContent).toContain(
      "答案ページがありません",
    );
    expect(screen.queryByTestId("review-page-surface")).toBeNull();
    expect(screen.getByTestId("review-page-indicator").textContent).toBe(
      "0 / 0",
    );
  });

  it("says the page image could not be loaded instead of staying silent", async () => {
    renderPdfReview({ pageImageFails: true });

    await waitFor(
      () => {
        expect(screen.getByTestId("review-page-surface")).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    expect(waitForRegion()).toBeDefined();
    expect(screen.getByTestId("review-page-surface").textContent).toContain(
      "ページ画像を読み込めませんでした",
    );
  });

  it("moves to the selected question's page without dropping the region", async () => {
    renderPdfReview({
      questions: [
        buildQuestion({ id: "q-1", number: "1", page: 1 }),
        buildQuestion({ id: "q-2", number: "2", page: 2 }),
      ],
      pages: [
        { displayed_width: 595, displayed_height: 842 },
        { displayed_width: 595, displayed_height: 842 },
      ],
      grades: [],
    });

    await waitFor(
      () => {
        expect(screen.getByTestId("review-rail-q-2")).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    expect(screen.getByTestId("review-page-indicator").textContent).toBe(
      "1 / 2",
    );

    fireEvent.click(screen.getByTestId("review-rail-q-2"));

    await waitFor(
      () => {
        expect(screen.getByTestId("review-page-indicator").textContent).toBe(
          "2 / 2",
        );
      },
      { timeout: WAIT_MS },
    );
    // Switching questions must not remove the viewer.
    expect(waitForRegion()).toBeDefined();
    expect(screen.getByTestId("review-page-surface")).toBeDefined();
  });

  it("clamps a question page that is out of range instead of blanking", async () => {
    renderPdfReview({
      questions: [buildQuestion({ id: "q-1", number: "1", page: 5 })],
      pages: [
        { displayed_width: 595, displayed_height: 842 },
        { displayed_width: 595, displayed_height: 842 },
      ],
      grades: [],
    });

    await waitFor(
      () => {
        expect(screen.getByTestId("review-page-indicator").textContent).toBe(
          "2 / 2",
        );
      },
      { timeout: WAIT_MS },
    );
    expect(screen.getByTestId("review-page-surface")).toBeDefined();
  });

  it("flips pages directly, independent of the selected question", async () => {
    renderPdfReview({
      pages: [
        { displayed_width: 595, displayed_height: 842 },
        { displayed_width: 595, displayed_height: 842 },
        { displayed_width: 595, displayed_height: 842 },
      ],
    });

    const indicator = () =>
      screen.getByTestId("review-page-indicator").textContent;
    await waitFor(
      () => {
        expect(indicator()).toBe("1 / 3");
      },
      { timeout: WAIT_MS },
    );
    expect(
      (screen.getByTestId("review-page-prev") as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByTestId("review-page-next") as HTMLButtonElement).disabled,
    ).toBe(false);

    fireEvent.click(screen.getByTestId("review-page-next"));
    expect(indicator()).toBe("2 / 3");
    fireEvent.click(screen.getByTestId("review-page-next"));
    expect(indicator()).toBe("3 / 3");
    expect(
      (screen.getByTestId("review-page-next") as HTMLButtonElement).disabled,
    ).toBe(true);

    fireEvent.click(screen.getByTestId("review-page-prev"));
    expect(indicator()).toBe("2 / 3");
    // The question selection never changed, yet the page did.
    expect(screen.getByTestId("review-rail-q-1").className).toContain(
      "border-primary",
    );
  });

  it("keeps the grading controls visible next to the page region", async () => {
    renderPdfReview({ grades: [buildGrade()] });

    await waitFor(
      () => {
        expect(screen.getByTestId("review-score")).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    expect(screen.getByTestId("review-page-surface")).toBeDefined();
    expect(screen.getByTestId("review-approve-button")).toBeDefined();
    expect(screen.getByTestId("review-reject-button")).toBeDefined();
    expect(screen.getByTestId("review-note-field")).toBeDefined();
  });
});
