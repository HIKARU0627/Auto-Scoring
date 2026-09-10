import type { SidecarClient } from "./client.js";
import {
  loadJobs,
  loadQuestionReviewData,
  loadQuestions,
  loadSubmission,
  PdfReviewDataError,
} from "./pdf-review-data.js";
import type { components } from "./generated/schema.js";
import {
  loadSubmissionQueueData,
  type SubmissionQueueData,
} from "./submission-queue-data.js";

export type SubmissionResponse = components["schemas"]["SubmissionResponse"];
export type QuestionResponse = components["schemas"]["QuestionResponse"];
export type JobResponse = components["schemas"]["JobResponse"];
export type QuestionReviewData = Awaited<
  ReturnType<typeof loadQuestionReviewData>
>;

export class SubmissionConfirmDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SubmissionConfirmDataError";
  }
}

export interface SubmissionConfirmData {
  readonly submission: SubmissionResponse;
  readonly questions: readonly QuestionResponse[];
  readonly jobs: readonly JobResponse[];
  readonly queue: SubmissionQueueData["queue"] | null;
}

export async function loadSubmissionConfirmData(
  client: SidecarClient,
  testId: string,
  submissionId: string,
): Promise<SubmissionConfirmData> {
  try {
    const [submission, questions, jobs] = await Promise.all([
      loadSubmission(client, submissionId),
      loadQuestions(client, testId),
      loadJobs(client, submissionId).catch(() => [] as JobResponse[]),
    ]);

    let queue: SubmissionQueueData["queue"] | null = null;
    try {
      const queueData = await loadSubmissionQueueData(client, testId);
      queue = queueData.queue;
    } catch {
      queue = null;
    }

    return { submission, questions, jobs, queue };
  } catch (error) {
    if (error instanceof PdfReviewDataError) {
      throw new SubmissionConfirmDataError(error.message);
    }
    throw error;
  }
}

export async function approveQuestionReview(
  client: SidecarClient,
  submissionId: string,
  question: {
    readonly questionId: string;
    readonly expectedVersion: number;
    readonly aiGradeId: string | null;
  },
): Promise<void> {
  const result = await client.POST(
    "/submissions/{submission_id}/questions/{question_id}/review/approve",
    {
      params: {
        path: {
          submission_id: submissionId,
          question_id: question.questionId,
        },
      },
      body: {
        expected_version: question.expectedVersion,
        expected_ai_grade_id: question.aiGradeId,
      },
    },
  );
  if (result.error !== undefined) {
    const message =
      typeof result.error === "object" &&
      result.error != null &&
      "message" in result.error &&
      typeof result.error.message === "string"
        ? result.error.message
        : "確定に失敗しました";
    throw new SubmissionConfirmDataError(message);
  }
}
