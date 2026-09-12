/**
 * Every location the app can be at, as the paths the router declares and
 * features navigate to (`docs/technology-stack.md` §2).
 *
 * Only the paths live here, not the route table: building a route means naming
 * a page, and `core` must not import `features` (`AGENTS.md` "Architecture").
 */
export const AppRoutes = {
  home: "/",
  starting: "/starting",
  intake: "/intake",
  settings: "/settings",
  testList: "/tests",
  testSettingsPattern: "/tests/:testId/settings",
  submissionQueuePattern: "/tests/:testId/submissions",
  submissionConfirmPattern: "/tests/:testId/submissions/:submissionId/confirm",
  pdfReviewPattern: "/tests/:testId/submissions/:submissionId/review",
  pdfReviewQuestionParam: "question",
  /**
   * `AppRoutes.intake` に添える「取り込み先テスト」の指定 (Issue #414).
   * テスト一覧・答案キュー・テスト設定の「答案を取り込む」から、そのテストが
   * 取り込み先として選ばれた状態で取込画面を開くために使う。
   */
  intakeTargetParam: "targetTestId",
} as const;

/**
 * 取込画面を、指定したテストが取り込み先として選ばれた状態で開く URL
 * (Issue #414)。テストが無い空状態からは `AppRoutes.intake` をそのまま使う。
 */
export function intakeTarget(testId: string): string {
  return `${AppRoutes.intake}?${AppRoutes.intakeTargetParam}=${encodeURIComponent(testId)}`;
}

/**
 * location から取込先テストの指定を読み出す (Issue #414)。指定が無い・空なら
 * `null`。ルーターは `params` にクエリを載せないので、画面側はここで読む。
 */
export function readIntakeTarget(location: string): string | null {
  const queryIndex = location.indexOf("?");
  if (queryIndex === -1) {
    return null;
  }
  const value = new URLSearchParams(location.slice(queryIndex)).get(
    AppRoutes.intakeTargetParam,
  );
  return value === null || value.length === 0 ? null : value;
}

export function testSettings(testId: string): string {
  return `/tests/${encodeURIComponent(testId)}/settings`;
}

export function submissionQueue(testId: string): string {
  return `/tests/${encodeURIComponent(testId)}/submissions`;
}

export function submissionConfirm(
  testId: string,
  submissionId: string,
): string {
  return `/tests/${encodeURIComponent(testId)}/submissions/${encodeURIComponent(submissionId)}/confirm`;
}

export function pdfReview(
  testId: string,
  submissionId: string,
  questionId?: string,
): string {
  const path = `/tests/${encodeURIComponent(testId)}/submissions/${encodeURIComponent(submissionId)}/review`;
  if (questionId === undefined) {
    return path;
  }
  return `${path}?${AppRoutes.pdfReviewQuestionParam}=${encodeURIComponent(questionId)}`;
}

/** Top-level route patterns declared in the route table (no query strings). */
export const declaredRoutePatterns: readonly string[] = [
  AppRoutes.home,
  AppRoutes.starting,
  AppRoutes.intake,
  AppRoutes.settings,
  AppRoutes.testList,
  AppRoutes.testSettingsPattern,
  AppRoutes.submissionQueuePattern,
  AppRoutes.submissionConfirmPattern,
  AppRoutes.pdfReviewPattern,
];
