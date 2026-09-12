import { describe, expect, it } from "vitest";

import {
  SCORE_PLACEMENT_MARGIN,
  SCORE_PLACEMENT_NONE,
  SCORE_PLACEMENT_OWN,
  commentDestination,
  hasNoRoomForScore,
  scoreOverlay,
} from "../../src/renderer/core/export-parity.js";
import type { QuestionScorePlacement } from "../../src/renderer/core/export-parity.js";

/**
 * Issue #406. The placement itself comes from the sidecar
 * (`domain.pdf_export.score_placements`); these tests pin only the two things
 * this module is allowed to do with it -- format the text the export draws and
 * answer "refused?" -- so it cannot silently invent a fourth outcome.
 */

const OWN_RECT = { x: 0.8, y: 0.6, width: 0.2, height: 0.05 };
const MARGIN_RECT = { x: 0.005, y: 0.05, width: 0.03, height: 0.05 };

const GRADE = { score: { awarded: 4, maximum: 5 } };

describe("scoreOverlay (Issue #406)", () => {
  it("places an own-area score at score_area with just awarded/maximum", () => {
    const placement: QuestionScorePlacement = {
      target: SCORE_PLACEMENT_OWN,
      rect: OWN_RECT,
    };

    expect(
      scoreOverlay({ placement, grade: GRADE, questionNumber: "問1" }),
    ).toEqual({
      rect: OWN_RECT,
      text: "4/5",
      placement: SCORE_PLACEMENT_OWN,
    });
  });

  it("places a margin score in the fallback strip, naming the question", () => {
    const placement: QuestionScorePlacement = {
      target: SCORE_PLACEMENT_MARGIN,
      rect: MARGIN_RECT,
    };

    // `_fallback_score_text`: score first, then the question it belongs to.
    expect(
      scoreOverlay({ placement, grade: GRADE, questionNumber: "問2" }),
    ).toEqual({
      rect: MARGIN_RECT,
      text: "4/5 問2",
      placement: SCORE_PLACEMENT_MARGIN,
    });
  });

  it("draws nothing for a refused score, even though the grade exists", () => {
    const placement: QuestionScorePlacement = {
      target: SCORE_PLACEMENT_NONE,
      rect: null,
    };

    expect(
      scoreOverlay({ placement, grade: GRADE, questionNumber: "問3" }),
    ).toBeNull();
  });

  it("draws nothing before there is a grade", () => {
    const placement: QuestionScorePlacement = {
      target: SCORE_PLACEMENT_OWN,
      rect: OWN_RECT,
    };

    expect(
      scoreOverlay({ placement, grade: null, questionNumber: "問1" }),
    ).toBeNull();
  });
});

describe("hasNoRoomForScore (Issue #406)", () => {
  it("is true only for the sidecar's none target", () => {
    expect(
      hasNoRoomForScore({ target: SCORE_PLACEMENT_NONE, rect: null }),
    ).toBe(true);
    expect(
      hasNoRoomForScore({ target: SCORE_PLACEMENT_OWN, rect: OWN_RECT }),
    ).toBe(false);
    expect(
      hasNoRoomForScore({ target: SCORE_PLACEMENT_MARGIN, rect: MARGIN_RECT }),
    ).toBe(false);
    expect(hasNoRoomForScore(null)).toBe(false);
    expect(hasNoRoomForScore(undefined)).toBe(false);
  });
});

describe("commentDestination (Issue #406)", () => {
  it("uses the placed band when the question has a comment_area", () => {
    expect(commentDestination(OWN_RECT)).toBe("band");
  });

  it("falls back to the appended note page when it has none", () => {
    expect(commentDestination(null)).toBe("note-page");
    expect(commentDestination(undefined)).toBe("note-page");
  });
});
