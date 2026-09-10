/**
 * API data operations for the submission queue screen (Issue #113 / Issue #242).
 *
 * Uses the generated OpenAPI client only — no hand-written fetch.
 */

import type { SidecarClient } from "./client.js";
import type { components } from "./generated/schema.js";
import { ReviewQueue } from "../core/review-queue.js";

export type TestResponse = components["schemas"]["TestResponse"];
export type SubmissionResponse = components["schemas"]["SubmissionResponse"];
export type SubmissionReviewProgressResponse =
  components["schemas"]["SubmissionReviewProgressResponse"];
export type ExportRequestResponse =
  components["schemas"]["ExportRequestResponse"];
export type ExportResponse = components["schemas"]["ExportResponse"];
export type JobResponse = components["schemas"]["JobResponse"];

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

/**
 * Requests PDF export for a single submission (INV-145).
 */
export async function requestSubmissionExport(
  client: SidecarClient,
  submissionId: string,
): Promise<ExportRequestResponse> {
  const response = await client.POST("/submissions/{submission_id}/export", {
    params: { path: { submission_id: submissionId } },
  });

  if (response.error !== undefined || response.data === undefined) {
    const msg =
      typeof response.error === "object" &&
      response.error !== null &&
      "message" in response.error
        ? String(response.error.message)
        : "PDF出力の要求に失敗しました";
    throw new SubmissionQueueDataError(msg);
  }

  return response.data;
}

/**
 * Polls job status for export jobs.
 */
export async function getJob(
  client: SidecarClient,
  jobId: string,
): Promise<JobResponse> {
  const response = await client.GET("/jobs/{job_id}", {
    params: { path: { job_id: jobId } },
  });

  if (response.error !== undefined || response.data === undefined) {
    throw new SubmissionQueueDataError("ジョブ状態の取得に失敗しました");
  }

  return response.data;
}
