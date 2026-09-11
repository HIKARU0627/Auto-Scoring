/**
 * API data operations for the submission queue screen (Issue #113 / Issue #242).
 *
 * Uses the generated OpenAPI client only — no hand-written fetch.
 */

import type { components } from "../api/generated/schema.js";
import { ReviewQueue } from "./review-queue.js";
import type { SidecarClient } from "../api/client.js";

export type TestResponse = components["schemas"]["TestResponse"];
export type SubmissionResponse = components["schemas"]["SubmissionResponse"];
export type SubmissionReviewProgressResponse =
  components["schemas"]["SubmissionReviewProgressResponse"];
export type {
  ExportRequestResponse,
  ExportResponse,
  JobResponse,
} from "./export-data.js";
export { getJob, requestSubmissionExport } from "./export-data.js";

export class SubmissionQueueDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SubmissionQueueDataError";
  }
}

export interface SubmissionQueueData {
  readonly test: TestResponse;
  readonly queue: ReviewQueue;
}

/**
 * Loads test metadata, submissions, and per-question progress.
 *
 * If progress retrieval fails, falls back gracefully to empty progress:
 * missing question counts is lighter than failing the entire screen.
 */
export async function loadSubmissionQueueData(
  client: SidecarClient,
  testId: string,
): Promise<SubmissionQueueData> {
  const [testResponse, submissionsResponse] = await Promise.all([
    client.GET("/tests/{test_id}", {
      params: { path: { test_id: testId } },
    }),
    client.GET("/tests/{test_id}/submissions", {
      params: { path: { test_id: testId } },
    }),
  ]);

  if (testResponse.error !== undefined || testResponse.data === undefined) {
    const msg =
      typeof testResponse.error === "object" &&
      testResponse.error !== null &&
      "message" in testResponse.error
        ? String(testResponse.error.message)
        : "テストの取得に失敗しました";
    throw new SubmissionQueueDataError(msg);
  }

  if (
    submissionsResponse.error !== undefined ||
    submissionsResponse.data === undefined
  ) {
    const msg =
      typeof submissionsResponse.error === "object" &&
      submissionsResponse.error !== null &&
      "message" in submissionsResponse.error
        ? String(submissionsResponse.error.message)
        : "答案の一覧を取得できません";
    throw new SubmissionQueueDataError(msg);
  }

  let progress: SubmissionReviewProgressResponse[] = [];
  try {
    const progressResponse = await client.GET(
      "/tests/{test_id}/review-progress",
      {
        params: { path: { test_id: testId } },
      },
    );
    if (progressResponse.data !== undefined) {
      progress = progressResponse.data;
    }
  } catch {
    progress = [];
  }

  return {
    test: testResponse.data,
    queue: ReviewQueue.from({
      submissions: submissionsResponse.data,
      progress,
    }),
  };
}
