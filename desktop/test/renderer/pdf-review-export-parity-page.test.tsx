import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  buildGrade,
  buildQuestion,
  renderPdfReview,
} from "./support/pdf-review-harness.js";

/**
 * Issue #406 at the page level: the review screen must let the reviewer see
 * where the confirmed score will be printed, and must call out the questions
 * whose score has nowhere to go *before* an export is attempted. Both values
 * come straight from `QuestionResponse.score_placement`, which the sidecar
 * fills with `domain.pdf_export.score_placements`.
 */

describe("PdfReviewPage score placement (Issue #406)", () => {
  it("draws the score at the question's own score_area", async () => {
    renderPdfReview({
      questions: [
        buildQuestion({
          id: "q-1",
          number: "1",
          score_placement: {
            target: "own",
            rect: { x: 0.8, y: 0.6, width: 0.2, height: 0.05 },
          },
        }),
      ],
      grades: [buildGrade({ score: { awarded: 4, maximum: 5, ratio: 0.8 } })],
    });

    await waitFor(() => {
      expect(screen.getByTestId("review-score-overlay")).toBeDefined();
    });
    const overlay = screen.getByTestId("review-score-overlay");
    expect(overlay.textContent).toContain("4/5");
    expect(overlay.getAttribute("data-placement")).toBe("own");
  });

  it("draws the margin score with the question reference", async () => {
    renderPdfReview({
      questions: [
        buildQuestion({
          id: "q-1",
          number: "問1",
          score_placement: {
            target: "margin",
            rect: { x: 0.005, y: 0.05, width: 0.03, height: 0.05 },
          },
        }),
      ],
      grades: [buildGrade({ score: { awarded: 4, maximum: 5, ratio: 0.8 } })],
    });

    await waitFor(() => {
      expect(screen.getByTestId("review-score-overlay")).toBeDefined();
    });
    expect(screen.getByTestId("review-score-overlay").textContent).toContain(
      "4/5 問1",
    );
  });
});

describe("PdfReviewPage no_room_for_score (Issue #406)", () => {
  it("warns on the spotted question and marks it in the rail, before any export", async () => {
    renderPdfReview({
      questions: [
        buildQuestion({
          id: "q-1",
          number: "1",
          score_placement: { target: "none", rect: null },
        }),
        buildQuestion({
          id: "q-2",
          number: "2",
          score_placement: {
            target: "own",
            rect: { x: 0.8, y: 0.6, width: 0.2, height: 0.05 },
          },
        }),
      ],
      grades: [buildGrade()],
    });

    await waitFor(() => {
      expect(screen.getByTestId("review-no-room-for-score")).toBeDefined();
    });
    expect(
      screen.getByTestId("review-no-room-for-score").textContent,
    ).toContain("この答案はPDF出力できません");
    // No score overlay: the export will refuse rather than draw it.
    expect(screen.queryByTestId("review-score-overlay")).toBeNull();

    // Visible from the rail without opening the question.
    expect(screen.getByTestId("review-rail-no-room-q-1")).toBeDefined();
    expect(
      screen
        .getByTestId("review-rail-q-1")
        .getAttribute("data-no-room-for-score"),
    ).toBe("true");
    expect(screen.queryByTestId("review-rail-no-room-q-2")).toBeNull();
  });

  it("does not warn when the sidecar reports a placeable score", async () => {
    renderPdfReview({
      questions: [
        buildQuestion({
          id: "q-1",
          number: "1",
          score_placement: {
            target: "margin",
            rect: { x: 0.005, y: 0.05, width: 0.03, height: 0.05 },
          },
        }),
      ],
      grades: [buildGrade()],
    });

    await waitFor(() => {
      expect(screen.getByTestId("review-score-overlay")).toBeDefined();
    });
    expect(screen.queryByTestId("review-no-room-for-score")).toBeNull();
  });
});
