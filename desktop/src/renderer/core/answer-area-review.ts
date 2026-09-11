import type { components } from "../api/generated/schema.js";

type RegionModel = components["schemas"]["RegionModel"];

/**
 * Questions with no 回答欄, split by why (Issue #164).
 *
 * `regions` is the working copy being edited. `reportedAbsent` is the last
 * server response's absent list — what detection said, which does not change
 * as the reviewer edits.
 */
export function missingAnswerAreas(input: {
  regions: readonly RegionModel[];
  questionNumbers: readonly string[];
  reportedAbsent: ReadonlySet<string>;
}): { undetected: string[]; absent: string[] } {
  const covered = new Set(
    input.regions
      .filter((region) => region.kind === "answer_area")
      .map((region) => region.label),
  );
  const undetected: string[] = [];
  const absent: string[] = [];
  for (const number of input.questionNumbers) {
    if (covered.has(number)) {
      continue;
    }
    (input.reportedAbsent.has(number) ? absent : undetected).push(number);
  }
  return { undetected, absent };
}

/** Answer areas that name no confirmed question. */
export function unassignedAnswerAreas(input: {
  regions: readonly RegionModel[];
  knownQuestionNumbers: ReadonlySet<string>;
}): RegionModel[] {
  return input.regions.filter(
    (region) =>
      region.kind === "answer_area" &&
      !input.knownQuestionNumbers.has(region.label),
  );
}

/**
 * How much of the criteria's question list the registered answer areas cover
 * (Issue #314).
 *
 * `uncovered` is every criteria question with no `answer_area` region,
 * whether detection declared it absent from the sheet or simply never found a
 * box for it. The screen shows this so a reviewer can see that the registered
 * pages are only part of the assignment before confirming the profile.
 */
export function answerAreaCoverage(input: {
  questionNumbers: readonly string[];
  regions: readonly RegionModel[];
}): { expected: number; covered: number; uncovered: number } {
  const coveredLabels = new Set(
    input.regions
      .filter((region) => region.kind === "answer_area")
      .map((region) => region.label),
  );
  const covered = input.questionNumbers.filter((number) =>
    coveredLabels.has(number),
  ).length;
  return {
    expected: input.questionNumbers.length,
    covered,
    uncovered: input.questionNumbers.length - covered,
  };
}

/**
 * Whether profile confirm must wait until the answer sheet is visible on screen.
 * Empty region lists do not open the gate — that is a separate requirement.
 */
export function mustSeeAnswerSheetFirst(input: {
  answerSheetVisible: boolean;
  regions: readonly RegionModel[];
}): boolean {
  return (
    !input.answerSheetVisible &&
    input.regions.some((region) => region.kind === "answer_area")
  );
}
