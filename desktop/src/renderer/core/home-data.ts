import type { SidecarClient } from "../api/client.js";
import { HomeDashboard } from "./home-dashboard.js";
import type {
  SubmissionResponse,
  SubmissionReviewProgressResponse,
  TestResponse,
} from "./home-dashboard.js";

export class HomeDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HomeDataError";
  }
}

/**
 * Loads every test registration and all of their submissions for the home
 * dashboard. Uses the generated OpenAPI client only — no hand-written fetch.
 *
 * A failure to list the *tests* is fatal: without them there is no dashboard.
 * A per-test failure is not (Issue #336): the test still appears in the table,
 * its counts are marked as unavailable, and `HomeDashboard.degradedTests`
 * names what could not be read so the screen can say so instead of drawing a
 * fabricated `0`.
 */
export async function loadHomeDashboard(
  client: SidecarClient,
  now: Date = new Date(),
): Promise<HomeDashboard> {
  const registrations = await client.GET("/test-registrations");
  if (registrations.error !== undefined) {
    throw new HomeDataError("作業状況を取得できません");
  }

  const tests: readonly TestResponse[] = registrations.data;
  const submissionsByTestId: Record<string, readonly SubmissionResponse[]> = {};
  const reviewProgressByTestId: Record<
    string,
    readonly SubmissionReviewProgressResponse[]
  > = {};
  const unavailableSubmissionTestIds: string[] = [];
  const unavailableReviewProgressTestIds: string[] = [];

  await Promise.all(
    tests.map(async (test) => {
      const submissions = await client.GET("/tests/{test_id}/submissions", {
        params: { path: { test_id: test.id } },
      });
      if (submissions.error !== undefined) {
        unavailableSubmissionTestIds.push(test.id);
      } else {
        submissionsByTestId[test.id] = submissions.data;
      }

      const reviewProgress = await client.GET(
        "/tests/{test_id}/review-progress",
        {
          params: { path: { test_id: test.id } },
        },
      );
      if (reviewProgress.error !== undefined) {
        unavailableReviewProgressTestIds.push(test.id);
      } else {
        reviewProgressByTestId[test.id] = reviewProgress.data;
      }
    }),
  );

  return HomeDashboard.from({
    tests,
    submissionsByTestId,
    unavailableSubmissionTestIds,
    reviewProgressByTestId,
    unavailableReviewProgressTestIds,
    now,
  });
}
