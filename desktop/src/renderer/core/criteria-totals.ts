import type { components } from "../api/generated/schema.js";

type CriteriaQuestionModel = components["schemas"]["CriteriaQuestionModel"];

export interface CriteriaTotals {
  readonly knownPoints: number;
  readonly unknownCount: number;
  readonly declaredTotalPoints: number | null;
  readonly declaredDifference: number | null;
}

/** Aggregate points from the editable list, not from the last server snapshot. */
export function criteriaTotals(
  questions: readonly CriteriaQuestionModel[],
  input: { declaredTotalPoints?: number | null } = {},
): CriteriaTotals {
  let knownPoints = 0;
  let unknownCount = 0;
  for (const question of questions) {
    if (question.points === null || question.points === undefined) {
      unknownCount += 1;
    } else {
      knownPoints += question.points;
    }
  }
  const declaredTotalPoints = input.declaredTotalPoints ?? null;
  const declaredDifference =
    declaredTotalPoints !== null &&
    unknownCount === 0 &&
    declaredTotalPoints !== knownPoints
      ? declaredTotalPoints - knownPoints
      : null;
  return {
    knownPoints,
    unknownCount,
    declaredTotalPoints,
    declaredDifference,
  };
}

/** Returns why criteria cannot be confirmed, or null when confirm is allowed. */
export function criteriaBlockingReason(
  questions: readonly CriteriaQuestionModel[],
): string | null {
  if (questions.length === 0) {
    return "設問が 1 件もありません。抽出をやり直すか、設問を手で追加してください。";
  }
  const unknown = questions.filter(
    (question) => question.points === null || question.points === undefined,
  ).length;
  if (unknown > 0) {
    return `配点が不明の設問が ${unknown} 件あります。すべての配点を入力してください。`;
  }
  const nonPositive = questions.filter(
    (question) => (question.points ?? 0) <= 0,
  ).length;
  if (nonPositive > 0) {
    return `配点が 0 以下の設問が ${nonPositive} 件あります。1 以上を入力してください。`;
  }
  return null;
}

/** Whether a confirmed graph still describes the current question set. */
export function dependencyGraphDescribesQuestions(input: {
  testId: string;
  graphQuestionIds: readonly string[];
  criteriaNumbers: readonly string[];
  questionRegionLabels: readonly string[];
}): boolean {
  const expected = new Set<string>([
    ...input.criteriaNumbers.map((number) => `${input.testId}:${number}`),
    ...input.questionRegionLabels.map((label) => `${input.testId}:${label}`),
  ]);
  const actual = new Set(input.graphQuestionIds);
  return (
    expected.size === actual.size && [...expected].every((id) => actual.has(id))
  );
}
