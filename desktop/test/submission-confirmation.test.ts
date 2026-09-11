import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

import {
  createSubmissionConfirmation,
  runSubmissionConfirmation,
  SubmissionConfirmBlock,
  type QuestionConfirmation,
} from "../src/renderer/core/submission-confirmation.js";

function question(
  overrides: Partial<QuestionConfirmation> & {
    questionId?: string;
    number?: string;
  } = {},
): QuestionConfirmation {
  return {
    questionId: overrides.questionId ?? "q-1",
    number: overrides.number ?? "1",
    materialLoaded: overrides.materialLoaded ?? true,
    isConfirmed: overrides.isConfirmed ?? false,
    aiGradeId:
      overrides.aiGradeId !== undefined ? overrides.aiGradeId : "grade-1",
    expectedVersion: overrides.expectedVersion ?? 0,
    isReached: overrides.isReached ?? true,
  };
}

describe("SubmissionConfirmation (Issue #145 / INV-005, INV-154, INV-156, INV-157)", () => {
  it("INV-154: unreached questions block confirmation and are named", () => {
    const confirmation = createSubmissionConfirmation([
      question({ questionId: "q-1", number: "1" }),
      question({ questionId: "q-2", number: "2", isReached: false }),
      question({ questionId: "q-4", number: "4", isReached: false }),
    ]);

    expect(confirmation.canConfirm).toBe(false);
    expect(confirmation.blocker).toBe(SubmissionConfirmBlock.unreached);
    expect(confirmation.unreached.map((q) => q.number)).toEqual(["2", "4"]);
  });

  it("confirmed questions do not require reach again", () => {
    const confirmation = createSubmissionConfirmation([
      question({
        questionId: "q-1",
        number: "1",
        isConfirmed: true,
        isReached: false,
      }),
      question({ questionId: "q-2", number: "2" }),
    ]);

    expect(confirmation.canConfirm).toBe(true);
    expect(confirmation.unreached).toEqual([]);
    expect(confirmation.pending.map((q) => q.number)).toEqual(["2"]);
  });

  it("INV-157: human score required blocks even when reached", () => {
    const confirmation = createSubmissionConfirmation([
      question({ questionId: "q-1", number: "1" }),
      question({ questionId: "q-2", number: "2", aiGradeId: null }),
    ]);

    expect(confirmation.canConfirm).toBe(false);
    expect(confirmation.blocker).toBe(
      SubmissionConfirmBlock.humanScoreRequired,
    );
    expect(confirmation.needingHumanScore.map((q) => q.number)).toEqual(["2"]);
  });

  it("material unavailable takes precedence over unreached", () => {
    const confirmation = createSubmissionConfirmation([
      question({ questionId: "q-1", number: "1", materialLoaded: false }),
      question({ questionId: "q-2", number: "2", isReached: false }),
    ]);

    expect(confirmation.blocker).toBe(
      SubmissionConfirmBlock.materialUnavailable,
    );
  });
});

describe("runSubmissionConfirmation (INV-155, INV-156)", () => {
  it("approves all pending questions in order", async () => {
    const approved: string[] = [];
    const outcome = await runSubmissionConfirmation({
      questions: [
        question({ questionId: "q-1", number: "1" }),
        question({ questionId: "q-2", number: "2" }),
        question({ questionId: "q-3", number: "3" }),
      ],
      approve: async (q) => {
        approved.push(q.questionId);
      },
    });

    expect(approved).toEqual(["q-1", "q-2", "q-3"]);
    expect(outcome.confirmed).toEqual(["1", "2", "3"]);
    expect(outcome.failedNumber).toBeNull();
  });

  it("INV-156: stops at first failure and reports partial progress", async () => {
    const approved: string[] = [];
    const outcome = await runSubmissionConfirmation({
      questions: [
        question({ questionId: "q-1", number: "1" }),
        question({ questionId: "q-2", number: "2" }),
        question({ questionId: "q-3", number: "3" }),
        question({ questionId: "q-4", number: "4" }),
      ],
      approve: async (q) => {
        approved.push(q.questionId);
        if (q.questionId === "q-3") {
          throw new Error("他の操作と競合しました");
        }
      },
    });

    expect(approved).toEqual(["q-1", "q-2", "q-3"]);
    expect(outcome.confirmed).toEqual(["1", "2"]);
    expect(outcome.failedNumber).toBe("3");
    expect(outcome.message).toContain("競合");
    expect(outcome.remaining).toEqual(["3", "4"]);
  });
});

describe("INV-201-02: confidence must not enter confirmation logic", () => {
  it("submission-confirmation.ts contains no confidence identifier outside comments", () => {
    const source = readFileSync(
      path.join(
        import.meta.dirname,
        "../src/renderer/core/submission-confirmation.ts",
      ),
      "utf8",
    );
    const identifier = /\bconfidence\b/i;
    const offenders = source
      .split("\n")
      .filter(
        (line) =>
          identifier.test(line) &&
          !line.trimStart().startsWith("*") &&
          !line.trimStart().startsWith("//"),
      )
      .map((line) => line.trim());

    expect(offenders).toEqual([]);
  });
});

describe("INV-005: the confirmation rule lives in core/submission-confirmation", () => {
  it("the confirm screen reads the core rule instead of re-deriving it", () => {
    const source = readFileSync(
      path.join(
        import.meta.dirname,
        "../src/renderer/features/submission-confirm/SubmissionConfirmPage.tsx",
      ),
      "utf8",
    );

    // 確定してよいかの判定は core に置く（INV-005）。画面が条件を書き直したら、
    // この 2 つの参照が消えるか、core を経由しない判定が現れる。
    expect(source).toContain('from "../../core/submission-confirmation.js"');
    expect(source).toContain("createSubmissionConfirmation(");
    expect(source).toContain("runSubmissionConfirmation(");
    expect(source).toContain("confirmation.canConfirm");
    expect(source).toContain("confirmation.blocker");
  });
});

describe("INV-157: a confirmed question no longer needs a human score", () => {
  it("does not block on a confirmed question that lacks an AI grade", () => {
    const confirmation = createSubmissionConfirmation([
      question({
        questionId: "q-1",
        number: "1",
        isConfirmed: true,
        aiGradeId: null,
      }),
      question({ questionId: "q-2", number: "2" }),
    ]);

    expect(confirmation.needingHumanScore.map((q) => q.number)).toEqual([]);
    expect(confirmation.blocker).toBeNull();
    expect(confirmation.canConfirm).toBe(true);
  });
});
