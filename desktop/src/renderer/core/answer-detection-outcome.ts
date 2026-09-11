/**
 * Classify what happened when answer-area detection finishes with zero boxes.
 * Wording for each outcome lives in `action-requirements.ts`.
 */

export type AnswerDetectionOutcome = "none" | "zero-results" | "role-mismatch";

export function countAnswerAreaRegions(
  regions: readonly { kind: string }[],
): number {
  return regions.filter((region) => region.kind === "answer_area").length;
}

/** After a successful detect call, decide which zero-result story applies. */
export function classifyAnswerDetectionOutcome(input: {
  questionNumbers: readonly string[];
  regions: readonly { kind: string }[];
  absentQuestionNumbers: readonly string[];
}): AnswerDetectionOutcome {
  if (countAnswerAreaRegions(input.regions) > 0) {
    return "none";
  }
  const absent = new Set(input.absentQuestionNumbers);
  if (
    input.questionNumbers.length > 0 &&
    input.questionNumbers.every((number) => absent.has(number))
  ) {
    return "role-mismatch";
  }
  return "zero-results";
}
