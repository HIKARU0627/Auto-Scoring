import { describe, expect, it } from "vitest";

import {
  answerAreaUndefinedReason,
  describeReviewReason,
  hasNearlyBlankCrop,
  nearlyBlankCropReason,
  questionsFlaggedAs,
} from "../src/renderer/core/submission-review-reason.js";

describe("submission review reason (INV-158 / INV-159)", () => {
  describe("questionsFlaggedAs", () => {
    it("reads the ids of one reason (INV-158)", () => {
      expect(
        questionsFlaggedAs("crop_nearly_blank:q-1,q-2", nearlyBlankCropReason),
      ).toEqual(new Set(["q-1", "q-2"]));
    });

    it("reads one reason out of several clauses (INV-158)", () => {
      expect(
        questionsFlaggedAs(
          "answer_area_undefined:q-1;crop_nearly_blank:q-2,q-3",
          nearlyBlankCropReason,
        ),
      ).toEqual(new Set(["q-2", "q-3"]));
    });

    it("a different reason does not leak into this one (INV-158)", () => {
      expect(
        questionsFlaggedAs("answer_area_undefined:q-1", nearlyBlankCropReason),
      ).toEqual(new Set());
    });

    it("a reason that only shares a prefix does not match (INV-158)", () => {
      expect(
        questionsFlaggedAs("crop_nearly_blank_v2:q-1", nearlyBlankCropReason),
      ).toEqual(new Set());
    });

    it("null and empty are no flags, not an error (INV-158)", () => {
      expect(questionsFlaggedAs(null, nearlyBlankCropReason)).toEqual(
        new Set(),
      );
      expect(questionsFlaggedAs("", nearlyBlankCropReason)).toEqual(new Set());
      expect(questionsFlaggedAs(undefined, nearlyBlankCropReason)).toEqual(
        new Set(),
      );
    });

    it("an unparseable reason flags nothing (INV-159)", () => {
      expect(
        questionsFlaggedAs("something_new", nearlyBlankCropReason),
      ).toEqual(new Set());
      expect(questionsFlaggedAs(":q-1", nearlyBlankCropReason)).toEqual(
        new Set(),
      );
    });

    it("ignores blank ids and surrounding whitespace (INV-158)", () => {
      expect(
        questionsFlaggedAs(
          "crop_nearly_blank: q-1 , ,q-2",
          nearlyBlankCropReason,
        ),
      ).toEqual(new Set(["q-1", "q-2"]));
    });

    it("a coverage reason with a non-id value is not read as ids (INV-158)", () => {
      expect(
        questionsFlaggedAs(
          "missing_pages:2;extra_pages:3>2",
          nearlyBlankCropReason,
        ),
      ).toEqual(new Set());
    });

    it("treats unknown reason as empty set and does not guess (INV-159)", () => {
      // Must test with actual unknown reason strings
      const unknownReason = "future_sidecar_anomaly_detected:q-99,q-100";
      expect(
        questionsFlaggedAs(unknownReason, "future_sidecar_anomaly_detected"),
      ).toEqual(new Set(["q-99", "q-100"]));

      // Asking for known reasons against unknown payload yields nothing
      expect(questionsFlaggedAs(unknownReason, nearlyBlankCropReason)).toEqual(
        new Set(),
      );
      expect(
        questionsFlaggedAs(unknownReason, answerAreaUndefinedReason),
      ).toEqual(new Set());
    });
  });

  describe("hasNearlyBlankCrop", () => {
    it("is true only for the questions the sidecar flagged (INV-158)", () => {
      const reason = "answer_area_undefined:q-1;crop_nearly_blank:q-2";
      expect(hasNearlyBlankCrop(reason, "q-2")).toBe(true);
      expect(hasNearlyBlankCrop(reason, "q-1")).toBe(false);
      expect(hasNearlyBlankCrop(reason, "q-3")).toBe(false);
      expect(hasNearlyBlankCrop(null, "q-2")).toBe(false);
    });
  });

  describe("describeReviewReason", () => {
    it("formats known reasons into Japanese summary (INV-158)", () => {
      expect(
        describeReviewReason(
          "answer_area_undefined:q-1;crop_nearly_blank:q-2,q-3",
        ),
      ).toBe(
        "回答欄が確定できない設問が1問、切り出しがほぼ余白の設問が2問あります",
      );

      expect(describeReviewReason("answer_area_undefined:q-2")).toBe(
        "回答欄が確定できない設問が1問あります",
      );

      expect(describeReviewReason("crop_nearly_blank:q-5")).toBe(
        "切り出しがほぼ余白の設問が1問あります",
      );
    });

    it("returns null for null, empty, or whitespace (INV-158)", () => {
      expect(describeReviewReason(null)).toBeNull();
      expect(describeReviewReason("")).toBeNull();
      expect(describeReviewReason("   ")).toBeNull();
      expect(describeReviewReason(undefined)).toBeNull();
    });

    it("does not guess unknown reason and returns null when all are unknown (INV-159)", () => {
      // Must test with actual unknown values
      expect(
        describeReviewReason("completely_unknown_flag:q-1,q-2"),
      ).toBeNull();
      expect(
        describeReviewReason("unrecognized_future_code:123;weird_error:456"),
      ).toBeNull();
    });

    it("ignores unknown reasons in mixed payload without guessing (INV-158 / INV-159)", () => {
      const mixed =
        "unknown_flag_v3:q-9;crop_nearly_blank:q-1;another_alien_reason:q-2";
      expect(describeReviewReason(mixed)).toBe(
        "切り出しがほぼ余白の設問が1問あります",
      );
    });
  });
});
