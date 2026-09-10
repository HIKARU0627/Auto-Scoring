import { vi } from "vitest";
import { render, type RenderResult } from "@testing-library/react";

import type { SidecarClient } from "../../../src/renderer/api/client.js";
import type { components } from "../../../src/renderer/api/generated/schema.js";
import { submissionConfirm } from "../../../src/renderer/core/app-routes.js";
import { SidecarApiProvider } from "../../../src/renderer/api/SidecarApiProvider.js";
import { SubmissionConfirmPage } from "../../../src/renderer/features/submission-confirm/SubmissionConfirmPage.js";
import { ThemeProvider } from "../../../src/renderer/theme/ThemeProvider.js";
import { RouterProvider } from "../../../src/renderer/navigation/router.js";

type QuestionResponse = components["schemas"]["QuestionResponse"];
type JobResponse = components["schemas"]["JobResponse"];
type GradeResultResponse = components["schemas"]["GradeResultResponse"];
type ReviewResponse = components["schemas"]["ReviewResponse"];
type RecognitionResponse = components["schemas"]["RecognitionResponse"];
type SubmissionResponse = components["schemas"]["SubmissionResponse"];

export interface SubmissionConfirmHarnessOptions {
  testId?: string;
  submissionId?: string;
  numbers?: readonly string[];
  alreadyConfirmed?: ReadonlySet<string>;
  withoutAiGrade?: ReadonlySet<string>;
  approveReview?: (
    submissionId: string,
    questionId: string,
    body: { expected_version: number; expected_ai_grade_id?: string | null },
  ) => Promise<unknown>;
  queueSubmissions?: SubmissionResponse[];
  listQuestions?: () => Promise<QuestionResponse[]>;
  getSubmission?: () => Promise<SubmissionResponse>;
  listRecognitions?: (
    submissionId: string,
    questionId: string,
  ) => Promise<RecognitionResponse[]>;
}

const DEFAULT_TEST_ID = "test-1";
const DEFAULT_SUBMISSION_ID = "sub-1";

function buildQuestion(number: string, testId: string): QuestionResponse {
  return {
    id: `q-${number}`,
    test_id: testId,
    number,
    page: 1,
    points: 5,
    scoring_method: "additive",
    answer_area: null,
    rubric: [],
  };
}

function buildGrade(
  questionId: string,
  submissionId: string,
): GradeResultResponse {
  return {
    id: `grade-${questionId}`,
    submission_id: submissionId,
    question_id: questionId,
    source: "ai",
    confidence: 0.88,
    created_at: "2026-01-01T00:00:00Z",
    criteria: [],
    score: { awarded: 4, maximum: 5, ratio: 0.8 },
    comment: null,
    rationale: "理由の説明が不足しています。",
    answer_image_finding: null,
  };
}

function buildRecognition(
  questionId: string,
  submissionId: string,
): RecognitionResponse {
  return {
    id: `rec-${questionId}`,
    submission_id: submissionId,
    question_id: questionId,
    source: "ai",
    stage: "ocr",
    text: `${questionId} の答案本文。`,
    confidence: 0.91,
    created_at: "2026-01-01T00:00:00Z",
    boxes: [],
  };
}

function buildApprovedReview(
  questionId: string,
  submissionId: string,
): ReviewResponse {
  return {
    id: `review-${questionId}`,
    submission_id: submissionId,
    question_id: questionId,
    action: "approved",
    version: 1,
    ai_grade_result_id: `grade-${questionId}`,
    created_at: "2026-01-02T00:00:00Z",
    human_grade_result_id: null,
    note: null,
    regrade_job_id: null,
  };
}

export function createSubmissionConfirmClient(
  options: SubmissionConfirmHarnessOptions = {},
): SidecarClient {
  const testId = options.testId ?? DEFAULT_TEST_ID;
  const submissionId = options.submissionId ?? DEFAULT_SUBMISSION_ID;
  const numbers = options.numbers ?? ["1", "2", "3", "4", "5"];
  const confirmed = new Set(options.alreadyConfirmed ?? []);
  const questions =
    options.listQuestions != null
      ? null
      : numbers.map((number) => buildQuestion(number, testId));

  return {
    GET: vi.fn(async (path, init) => {
      if (path === "/submissions/{submission_id}") {
        if (options.getSubmission) {
          try {
            const data = await options.getSubmission();
            return { data, response: new Response(), error: undefined };
          } catch (error) {
            return {
              data: undefined,
              response: new Response(null, { status: 500 }),
              error: {
                message: error instanceof Error ? error.message : String(error),
              },
            };
          }
        }
        return {
          data: {
            id: submissionId,
            test_id: testId,
            state: "ai_processed",
            page_count: 1,
            student_label: "答案A",
            created_at: "2026-01-01T00:00:00Z",
            is_retry: false,
            original_filename: null,
            review_reason: null,
          },
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/tests/{test_id}/questions") {
        const data =
          options.listQuestions != null
            ? await options.listQuestions()
            : (questions ?? []);
        return { data, response: new Response(), error: undefined };
      }
      if (path === "/submissions/{submission_id}/jobs") {
        const data: JobResponse[] = numbers.map((number) => ({
          id: `job-q-${number}`,
          kind: "grading",
          submission_id: submissionId,
          question_id: `q-${number}`,
          state: "succeeded",
          usable: true,
          attempts: 1,
          max_attempts: 3,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        }));
        return { data, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/submissions") {
        const data =
          options.queueSubmissions ??
          ([
            {
              id: submissionId,
              test_id: testId,
              state: "ai_processed",
              page_count: 1,
              student_label: "答案A",
              created_at: "2026-01-01T00:00:00Z",
              is_retry: false,
              original_filename: null,
              review_reason: null,
            },
          ] satisfies SubmissionResponse[]);
        return { data, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/review-progress") {
        return { data: [], response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}") {
        return {
          data: {
            id: testId,
            name: "国語 第1回",
            status: "ready",
            created_at: "2026-01-01T00:00:00Z",
            subject: null,
          },
          response: new Response(),
          error: undefined,
        };
      }
      if (
        path ===
        "/submissions/{submission_id}/questions/{question_id}/recognitions"
      ) {
        const questionId = init?.params?.path?.question_id ?? "q-1";
        if (options.listRecognitions) {
          try {
            const data = await options.listRecognitions(
              submissionId,
              questionId,
            );
            return { data, response: new Response(), error: undefined };
          } catch (error) {
            return {
              data: undefined,
              response: new Response(null, { status: 500 }),
              error: {
                message: error instanceof Error ? error.message : String(error),
              },
            };
          }
        }
        return {
          data: [buildRecognition(questionId, submissionId)],
          response: new Response(),
          error: undefined,
        };
      }
      if (
        path === "/submissions/{submission_id}/questions/{question_id}/grades"
      ) {
        const questionId = init?.params?.path?.question_id ?? "q-1";
        const without = options.withoutAiGrade?.has(questionId) ?? false;
        return {
          data: without ? [] : [buildGrade(questionId, submissionId)],
          response: new Response(),
          error: undefined,
        };
      }
      if (
        path === "/submissions/{submission_id}/questions/{question_id}/reviews"
      ) {
        const questionId = init?.params?.path?.question_id ?? "q-1";
        return {
          data: confirmed.has(questionId)
            ? [buildApprovedReview(questionId, submissionId)]
            : [],
          response: new Response(),
          error: undefined,
        };
      }
      if (
        path ===
        "/submissions/{submission_id}/questions/{question_id}/annotations"
      ) {
        return { data: [], response: new Response(), error: undefined };
      }
      if (
        path ===
        "/submissions/{submission_id}/questions/{question_id}/answer-image"
      ) {
        const blob = new Blob([new Uint8Array([137, 80, 78, 71])], {
          type: "image/png",
        });
        return { data: blob, response: new Response(), error: undefined };
      }
      return {
        data: undefined,
        response: new Response(null, { status: 404 }),
        error: { message: "not found" },
      };
    }),
    POST: vi.fn(async (path, init) => {
      if (
        path ===
        "/submissions/{submission_id}/questions/{question_id}/review/approve"
      ) {
        const questionId = init?.params?.path?.question_id ?? "q-1";
        if (options.approveReview) {
          try {
            const data = await options.approveReview(
              submissionId,
              questionId,
              init?.body ?? { expected_version: 0 },
            );
            confirmed.add(questionId);
            return { data, response: new Response(), error: undefined };
          } catch (error) {
            return {
              data: undefined,
              response: new Response(null, { status: 409 }),
              error: {
                message: error instanceof Error ? error.message : String(error),
              },
            };
          }
        }
        confirmed.add(questionId);
        return {
          data: {
            review: buildApprovedReview(questionId, submissionId),
            annotations: [],
            submission_state: "ai_processed",
          },
          response: new Response(),
          error: undefined,
        };
      }
      return {
        data: undefined,
        response: new Response(null, { status: 404 }),
        error: { message: "not found" },
      };
    }),
    PUT: vi.fn(),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
    use: vi.fn(),
    eject: vi.fn(),
  } as unknown as SidecarClient;
}

export function renderSubmissionConfirm(
  options: SubmissionConfirmHarnessOptions & { client?: SidecarClient } = {},
): RenderResult {
  const testId = options.testId ?? DEFAULT_TEST_ID;
  const submissionId = options.submissionId ?? DEFAULT_SUBMISSION_ID;
  const location = submissionConfirm(testId, submissionId);
  const client = options.client ?? createSubmissionConfirmClient(options);

  return render(
    <ThemeProvider>
      <SidecarApiProvider
        client={client}
        connection={{ host: "127.0.0.1", port: 1, token: "t" }}
      >
        <RouterProvider initialStack={[location]}>
          <SubmissionConfirmPage />
        </RouterProvider>
      </SidecarApiProvider>
    </ThemeProvider>,
  );
}
