/** Sidecar reason when the graded image is not this question's answer (Issue #136). */
export const NOT_THE_ANSWER_CROP_REASON = "crop_not_the_answer";

export function isNotTheAnswerCrop(
  lastError: string | null | undefined,
): boolean {
  return lastError != null && lastError.includes(NOT_THE_ANSWER_CROP_REASON);
}
