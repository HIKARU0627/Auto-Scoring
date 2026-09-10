import type { components } from "../api/generated/schema.js";
import {
  copyIntakeFile,
  type IntakeReviewState,
  withFile,
} from "./intake-review.js";

export type TestSummary = components["schemas"]["TestSummary"];

export function attributionCandidates(
  existingTests: readonly TestSummary[],
  narrowedTestIds: ReadonlySet<string>,
): readonly TestSummary[] {
  if (narrowedTestIds.size === 0) {
    return existingTests;
  }
  return existingTests.filter((test) => narrowedTestIds.has(test.id));
}

export function reviewerChoseOneTest(
  narrowedTestIds: ReadonlySet<string>,
  candidateCount: number,
): boolean {
  return narrowedTestIds.size === 1 && candidateCount === 1;
}

export function dropRoutingOutsideCandidates(
  review: IntakeReviewState,
  allowedTestIds: ReadonlySet<string>,
): IntakeReviewState {
  let next = review;
  for (const file of review.groups.flatMap((group) => group.files)) {
    const routed = file.answerTestId;
    const proposed = file.proposedAnswerTestId;
    const routedIsStale = routed !== null && !allowedTestIds.has(routed);
    const proposedIsStale = proposed !== null && !allowedTestIds.has(proposed);
    if (routedIsStale || proposedIsStale) {
      next = withFile(next, file.relativePath, (current) =>
        copyIntakeFile(current, {
          answerTestId: routedIsStale ? null : current.answerTestId,
          proposedAnswerTestId: proposedIsStale
            ? null
            : current.proposedAnswerTestId,
        }),
      );
    }
  }
  return next;
}
