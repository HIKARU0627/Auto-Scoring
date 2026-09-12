/**
 * The one path from 資料の取込 to PDF出力, named once (Issue #450).
 *
 * The owner could import materials but could not tell where they were or what
 * came next: the intake screen's own stepper stops at 取り込む, and the step
 * after that (テスト設定 → 答案の取込 → 採点の確認 → PDF出力) lived only in the
 * operator's head. This module names those five steps and the route each one
 * opens, so every screen can point at the same path instead of re-deriving it.
 *
 * Only the five steps live here, not the screens: a route is a path string from
 * `app-routes.ts`, and `core` must not import `features` (`AGENTS.md`
 * "Architecture").
 */

import { intakeTarget, submissionQueue, testSettings } from "./app-routes.js";

export const IntakeJourneyStage = {
  /** 採点基準と答案を選ぶ・取り込む (the intake screen itself). */
  materials: "materials",
  /** 配点・回答欄・設問依存関係を確定して `ready` にする. */
  settings: "settings",
  /** 登録済みテストへ答案を足し、AI採点を始める. */
  answers: "answers",
  /** AI採点の結果を1問ずつ確認する (答案キュー / 添削レビュー). */
  review: "review",
  /** 確定し終えた答案を PDF に出す. */
  export: "export",
} as const;

export type IntakeJourneyStage =
  (typeof IntakeJourneyStage)[keyof typeof IntakeJourneyStage];

export interface IntakeJourneyStep {
  readonly id: IntakeJourneyStage;
  readonly label: string;
}

/** The journey, in the order the operator has to walk it. */
export const INTAKE_JOURNEY: readonly IntakeJourneyStep[] = [
  { id: IntakeJourneyStage.materials, label: "資料の取込" },
  { id: IntakeJourneyStage.settings, label: "テスト設定" },
  { id: IntakeJourneyStage.answers, label: "答案の取込" },
  { id: IntakeJourneyStage.review, label: "採点の確認" },
  { id: IntakeJourneyStage.export, label: "PDF出力" },
];

export interface JourneyStepProgress {
  readonly id: string;
  readonly label: string;
  readonly complete: boolean;
}

export function journeyStepIndex(stage: IntakeJourneyStage): number {
  return INTAKE_JOURNEY.findIndex((step) => step.id === stage);
}

export function journeyLabel(stage: IntakeJourneyStage): string {
  return INTAKE_JOURNEY.find((step) => step.id === stage)?.label ?? stage;
}

/**
 * The stages up to and including [current], as `StepProgress` consumes them.
 * Every earlier stage is `complete`; the current one is left for the caller to
 * mark with `currentId`.
 */
export function journeySteps(
  current: IntakeJourneyStage,
): readonly JourneyStepProgress[] {
  const index = journeyStepIndex(current);
  return INTAKE_JOURNEY.map((step, stepIndex) => ({
    id: step.id,
    label: step.label,
    complete: stepIndex < index,
  }));
}

export interface JourneyProgress {
  /** `true` while the test is still `draft` (registration not confirmed). */
  readonly isDraft: boolean;
  /** Submissions loaded for the test, or `null` when the list failed to load. */
  readonly answerCount: number | null;
  /** Submissions the operator has fully confirmed. */
  readonly doneCount: number;
  /** Submissions known for the test. */
  readonly total: number;
}

/**
 * Which stage a registered test is on now, or `null` when the answer list could
 * not be read and the stage is genuinely unknown.
 *
 * A draft has not been through テスト設定. A ready test with no answers needs
 * 答案の取込; one with answers not yet all confirmed needs 採点の確認; once
 * every answer is confirmed the only step left is PDF出力.
 */
export function journeyStageForTest(
  progress: JourneyProgress,
): IntakeJourneyStage | null {
  if (progress.answerCount === null) {
    return null;
  }
  if (progress.isDraft) {
    return IntakeJourneyStage.settings;
  }
  if (progress.answerCount === 0) {
    return IntakeJourneyStage.answers;
  }
  if (progress.total > 0 && progress.doneCount >= progress.total) {
    return IntakeJourneyStage.export;
  }
  return IntakeJourneyStage.review;
}

/** The route a test's current stage opens, for a 「次へ」 button. */
export function journeyRoute(
  stage: IntakeJourneyStage,
  testId: string,
): string {
  switch (stage) {
    case IntakeJourneyStage.materials:
    case IntakeJourneyStage.answers:
      return intakeTarget(testId);
    case IntakeJourneyStage.settings:
      return testSettings(testId);
    case IntakeJourneyStage.review:
    case IntakeJourneyStage.export:
      return submissionQueue(testId);
  }
}
