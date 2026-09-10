/**
 * Reading `Submission.review_reason` (Issue #122 / INV-158 / INV-159).
 *
 * Wire format: `<reason>:<value>` clauses joined by `;`, where per-question reasons
 * carry a comma-separated list of question ids:
 * `answer_area_undefined:q-1;crop_nearly_blank:q-2,q-3`
 */

export const nearlyBlankCropReason = "crop_nearly_blank";
export const answerAreaUndefinedReason = "answer_area_undefined";

const REASON_LABELS: Readonly<Record<string, string>> = {
  [answerAreaUndefinedReason]: "回答欄が確定できない設問",
  [nearlyBlankCropReason]: "切り出しがほぼ余白の設問",
};

/**
 * Returns the set of question ids flagged with [reason] in [reviewReason].
 *
 * Returns an empty set for null, empty, or unparseable reasons.
 * Unknown reasons are never guessed at (INV-159).
 */
export function questionsFlaggedAs(
  reviewReason: string | null | undefined,
  reason: string,
): Set<string> {
  if (
    reviewReason === null ||
    reviewReason === undefined ||
    reviewReason.trim().length === 0
  ) {
    return new Set<string>();
  }

  const flagged = new Set<string>();
  for (const clause of reviewReason.split(";")) {
    const separator = clause.indexOf(":");
    if (separator <= 0) {
      continue;
    }
    const clauseReason = clause.substring(0, separator).trim();
    if (clauseReason !== reason) {
      continue;
    }
    const idsPart = clause.substring(separator + 1);
    for (const rawId of idsPart.split(",")) {
      const trimmed = rawId.trim();
      if (trimmed.length > 0) {
        flagged.add(trimmed);
      }
    }
  }

  return flagged;
}

/** Whether [questionId]'s crop was flagged as nearly blank. */
export function hasNearlyBlankCrop(
  reviewReason: string | null | undefined,
  questionId: string,
): boolean {
  return questionsFlaggedAs(reviewReason, nearlyBlankCropReason).has(
    questionId,
  );
}

/**
 * Turns machine-readable review_reason flags into a human-readable Japanese summary.
 *
 * Unknown reasons are ignored and never guessed at (INV-159).
 * If all reasons are unknown or no questions are flagged, returns null.
 */
export function describeReviewReason(
  reviewReason: string | null | undefined,
): string | null {
  if (
    reviewReason === null ||
    reviewReason === undefined ||
    reviewReason.trim().length === 0
  ) {
    return null;
  }

  const parts: string[] = [];
  for (const [reason, label] of Object.entries(REASON_LABELS)) {
    const count = questionsFlaggedAs(reviewReason, reason).size;
    if (count > 0) {
      parts.push(`${label}が${count}問`);
    }
  }

  if (parts.length === 0) {
    return null;
  }

  return `${parts.join("、")}あります`;
}
