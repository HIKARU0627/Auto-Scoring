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
} as const;

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
