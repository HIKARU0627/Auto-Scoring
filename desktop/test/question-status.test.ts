import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

import type { components } from "../src/renderer/api/generated/schema.js";
import {
  deriveQuestionStatus,
  jobIsInProgress,
} from "../src/renderer/core/question-status.js";

type JobResponse = components["schemas"]["JobResponse"];
type ReviewResponse = components["schemas"]["ReviewResponse"];

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");

function atUtc(seconds: number): string {
  return new Date(Date.UTC(2026, 1, 1, 0, 0, seconds)).toISOString();
}

function job(
  overrides: Partial<JobResponse> & {
    state?: string;
    usable?: boolean | null;
    createdAtSeconds?: number;
  } = {},
): JobResponse {
  const { createdAtSeconds = 0, usable, ...rest } = overrides;
  return {
    id: "job-q1",
    kind: "grading",
    submission_id: "sub-1",
    question_id: "q1",
    state: "running",
    blocked_on_question_id: null,
    attempts: 1,
    max_attempts: 3,
    created_at: atUtc(createdAtSeconds),
    updated_at: atUtc(createdAtSeconds),
    ...rest,
    ...(usable !== undefined ? { usable } : {}),
  };
}

function review(
  overrides: Partial<ReviewResponse> & {
    action?: string;
    createdAtSeconds?: number;
  } = {},
): ReviewResponse {
  const createdAtSeconds = overrides.createdAtSeconds ?? 0;
  return {
    id: overrides.id ?? "review-1",
    submission_id: "sub-1",
    question_id: overrides.question_id ?? "q1",
    action: overrides.action ?? "approved",
    version: 1,
    ai_grade_result_id: "grade-1",
    regrade_job_id: overrides.regrade_job_id ?? null,
    created_at: atUtc(createdAtSeconds),
    ...overrides,
  };
}

function derive(input: {
  job: JobResponse | null | undefined;
  review: ReviewResponse | null | undefined;
  hasWaitingDependents?: boolean;
}) {
  return deriveQuestionStatus({
    job: input.job,
    review: input.review,
    hasWaitingDependents: input.hasWaitingDependents ?? false,
  });
}

describe("deriveQuestionStatus", () => {
  describe("INV-152: usable=false branches on whether dependents are waiting", () => {
    it("returns needsCheck only when unusable and a dependent is blocked behind it", () => {
      const unusable = job({ state: "succeeded", usable: false });
      expect(
        derive({ job: unusable, review: null, hasWaitingDependents: true }),
      ).toBe("needsCheck");
      expect(
        derive({ job: unusable, review: null, hasWaitingDependents: false }),
      ).toBe("graded");
    });

    it("does not treat usable alone as needsCheck when nothing is waiting", () => {
      for (const usable of [true, false] as const) {
        expect(
          derive({
            job: job({ state: "succeeded", usable }),
            review: null,
            hasWaitingDependents: false,
          }),
        ).toBe("graded");
      }
    });

    it("keeps an approval recorded before the attempt when nothing is waiting", () => {
      for (const usable of [true, false] as const) {
        expect(
          derive({
            job: job({
              state: "succeeded",
              usable,
              createdAtSeconds: 2,
            }),
            review: review({ action: "approved", createdAtSeconds: 1 }),
            hasWaitingDependents: false,
          }),
        ).toBe("approved");
      }
    });
  });

  describe("INV-153: a human decision after a stopped job outranks the job state", () => {
    it("shows the review when it was recorded after the terminal job", () => {
      for (const state of ["failed", "cancelled", "succeeded"] as const) {
        expect(
          derive({
            job: job({
              state,
              usable: state === "succeeded" ? false : null,
              createdAtSeconds: 1,
            }),
            review: review({ action: "modified", createdAtSeconds: 2 }),
            hasWaitingDependents: true,
          }),
        ).toBe("approved");
      }
    });

    it("keeps the stopped job when the review predates it", () => {
      expect(
        derive({
          job: job({ state: "failed", usable: false, createdAtSeconds: 2 }),
          review: review({ action: "modified", createdAtSeconds: 1 }),
          hasWaitingDependents: true,
        }),
      ).toBe("failed");
      expect(
        derive({
          job: job({ state: "cancelled", createdAtSeconds: 2 }),
          review: review({ action: "modified", createdAtSeconds: 1 }),
          hasWaitingDependents: true,
        }),
      ).toBe("cancelled");
      expect(
        derive({
          job: job({
            state: "succeeded",
            usable: false,
            createdAtSeconds: 2,
          }),
          review: review({ action: "modified", createdAtSeconds: 1 }),
          hasWaitingDependents: true,
        }),
      ).toBe("needsCheck");
    });

    it("still lets a live job outrank an older review", () => {
      expect(
        derive({
          job: job({ state: "running", createdAtSeconds: 2 }),
          review: review({ action: "approved", createdAtSeconds: 1 }),
        }),
      ).toBe("running");
    });
  });
});

describe("INV-006: question status is derived centrally", () => {
  it("only tells a caller a job is in flight for non-terminal states (Issue #319)", () => {
    expect(jobIsInProgress(null)).toBe(false);
    expect(jobIsInProgress(undefined)).toBe(false);
    for (const state of ["queued", "running", "blocked"]) {
      expect(jobIsInProgress(job({ state }))).toBe(true);
    }
    for (const state of ["succeeded", "failed", "cancelled"]) {
      expect(jobIsInProgress(job({ state }))).toBe(false);
    }
  });

  const STATUS_SURFACES = [
    "src/renderer/features/pdf-review/PdfReviewPage.tsx",
    "src/renderer/features/submission-confirm/SubmissionConfirmPage.tsx",
    "src/renderer/core/dependency-dag.ts",
  ] as const;

  it("lists every surface that shows a per-question status", () => {
    expect(STATUS_SURFACES).toEqual([
      "src/renderer/features/pdf-review/PdfReviewPage.tsx",
      "src/renderer/features/submission-confirm/SubmissionConfirmPage.tsx",
      "src/renderer/core/dependency-dag.ts",
    ]);
  });

  it("routes each listed surface through deriveQuestionStatus", () => {
    const callPattern = /\bderiveQuestionStatus\s*\(/;
    for (const relativePath of STATUS_SURFACES) {
      const source = readFileSync(
        path.join(PACKAGE_ROOT, relativePath),
        "utf8",
      );
      expect(callPattern.test(source)).toBe(true);
    }
  });

  it("does not let feature screens map job.state to status keys inline", () => {
    const forbidden = [
      /\bcase\s+["']succeeded["']\s*:/,
      /\bjob\.state\s*===\s*["']succeeded["']/,
      /\bjob\.state\s*===\s*["']failed["']/,
      /\bjob\.state\s*===\s*["']running["']/,
    ];
    for (const relativePath of STATUS_SURFACES.filter((p) =>
      p.includes("/features/"),
    )) {
      const source = readFileSync(
        path.join(PACKAGE_ROOT, relativePath),
        "utf8",
      );
      const offenders = forbidden.filter((pattern) => pattern.test(source));
      expect(offenders).toEqual([]);
    }
  });
});
