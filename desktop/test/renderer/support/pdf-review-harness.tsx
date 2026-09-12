import { vi } from "vitest";
import { render, type RenderResult } from "@testing-library/react";

import type { SidecarClient } from "../../../src/renderer/api/client.js";
import type { components } from "../../../src/renderer/api/generated/schema.js";
import { SidecarApiProvider } from "../../../src/renderer/api/SidecarApiProvider.js";
import { PdfReviewPage } from "../../../src/renderer/features/pdf-review/PdfReviewPage.js";
import { ThemeProvider } from "../../../src/renderer/theme/ThemeProvider.js";
import { RouterProvider } from "../../../src/renderer/navigation/router.js";

type QuestionResponse = components["schemas"]["QuestionResponse"];
type JobResponse = components["schemas"]["JobResponse"];
type GradeResultResponse = components["schemas"]["GradeResultResponse"];
type ReviewResponse = components["schemas"]["ReviewResponse"];
type AnnotationResponse = components["schemas"]["AnnotationResponse"];
type RecognitionResponse = components["schemas"]["RecognitionResponse"];

type DependencyEdge = components["schemas"]["DependencyEdgeModel"];

export interface PdfReviewHarnessOptions {
  testId?: string;
  submissionId?: string;
  questionId?: string;
  questions?: QuestionResponse[];
  jobs?: JobResponse[];
  /**
   * Successive answers for `GET /submissions/{id}/jobs` (Issue #319). The
   * last entry repeats once the sequence is exhausted, so a test can hold a
   * job "running" and then let it finish.
   */
  jobsSequence?: JobResponse[][];
  edges?: DependencyEdge[];
  grades?: GradeResultResponse[];
  recognitions?: RecognitionResponse[];
  annotations?: AnnotationResponse[];
  reviews?: ReviewResponse[];
  criterionCount?: number;
  /**
   * Page geometries the submission reports (Issue #385). The default is one
   * page, so existing specs keep their single-page submission. An empty array
   * models a submission whose page images could not be produced at all.
   */
  pages?: Array<{ displayed_width: number; displayed_height: number }>;
  /** Return an error for every page-image request. */
  pageImageFails?: boolean;
  /** Keep the page in loading until `releaseInitialLoad` is called. */
  holdInitialLoad?: boolean;
  /** Keep question review data unloaded until `releaseQuestionData` is called. */
  holdQuestionData?: boolean;
}

export interface PdfReviewHarnessHandle {
  releaseInitialLoad: () => void;
  releaseQuestionData: () => void;
}

const DEFAULT_TEST_ID = "test-1";
const DEFAULT_SUBMISSION_ID = "sub-1";

export function buildQuestion(
  input: Partial<QuestionResponse> & { id: string; number: string },
): QuestionResponse {
  return {
    id: input.id,
    test_id: input.test_id ?? DEFAULT_TEST_ID,
    number: input.number,
    page: input.page ?? 1,
    points: input.points ?? 5,
    scoring_method: input.scoring_method ?? "additive",
    answer_area: input.answer_area ?? null,
    rubric: input.rubric ?? [],
  };
}

export function buildJob(
  input: Partial<JobResponse> & { state: string },
): JobResponse {
  return {
    id: input.id ?? "job-1",
    kind: input.kind ?? "grading",
    submission_id: input.submission_id ?? DEFAULT_SUBMISSION_ID,
    question_id: input.question_id ?? "q-1",
    state: input.state,
    usable: input.usable ?? null,
    attempts: input.attempts ?? 1,
    max_attempts: input.max_attempts ?? 3,
    created_at: input.created_at ?? "2026-01-01T00:00:00Z",
    updated_at: input.updated_at ?? "2026-01-01T00:00:00Z",
  };
}

export function buildGrade(
  input: Partial<GradeResultResponse> & { questionId?: string } = {},
): GradeResultResponse {
  const awarded = input.score?.awarded ?? 3;
  const maximum = input.score?.maximum ?? 5;
  const criteria = input.criteria ?? [];
  return {
    id: input.id ?? "grade-1",
    submission_id: input.submission_id ?? DEFAULT_SUBMISSION_ID,
    question_id: input.question_id ?? "q-1",
    source: input.source ?? "ai",
    confidence: input.confidence ?? 0.97,
    created_at: input.created_at ?? "2026-01-01T00:00:00Z",
    criteria,
    score: input.score ?? {
      awarded,
      maximum,
      ratio: awarded / maximum,
    },
    comment: input.comment ?? null,
    rationale: input.rationale ?? "採点理由",
    answer_image_finding: input.answer_image_finding ?? null,
  };
}

export function buildReviewableGrade(
  criterionCount: number,
): GradeResultResponse {
  const criteria = Array.from({ length: criterionCount }, (_, index) => ({
    criterion_id: `c-${index}`,
    outcome: `基準${index + 1}の判定`,
    confidence: 0.9,
  }));
  return buildGrade({ criteria });
}

function createLoadGate(enabled: boolean): {
  promise: Promise<void>;
  release: () => void;
} {
  if (!enabled) {
    return { promise: Promise.resolve(), release: () => {} };
  }
  let release = () => {};
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

export function createPdfReviewClient(options: PdfReviewHarnessOptions): {
  client: SidecarClient;
  handle: PdfReviewHarnessHandle;
} {
  const initialLoadGate = createLoadGate(options.holdInitialLoad === true);
  const questionDataGate = createLoadGate(options.holdQuestionData === true);
  const questions = options.questions ?? [
    buildQuestion({ id: "q-1", number: "1" }),
  ];
  const jobs = options.jobs ?? [
    {
      id: "job-1",
      kind: "grading",
      submission_id: DEFAULT_SUBMISSION_ID,
      question_id: "q-1",
      state: "succeeded",
      usable: true,
      attempts: 1,
      max_attempts: 3,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ];
  const grades = options.grades ?? [buildGrade()];
  const recognitions = options.recognitions ?? [
    {
      id: "rec-1",
      submission_id: DEFAULT_SUBMISSION_ID,
      question_id: "q-1",
      source: "ai",
      stage: "ocr",
      text: "答案",
      confidence: 0.55,
      created_at: "2026-01-01T00:00:00Z",
      boxes: [],
    },
  ];
  const annotations = options.annotations ?? [];
  const reviews = options.reviews ?? [];
  const pages = options.pages ?? [
    { displayed_width: 595, displayed_height: 842 },
  ];
  let jobsRead = 0;

  const client = {
    GET: vi.fn(async (path, _init) => {
      if (path === "/submissions/{submission_id}") {
        await initialLoadGate.promise;
        return {
          data: {
            id: DEFAULT_SUBMISSION_ID,
            test_id: DEFAULT_TEST_ID,
            state: "needs_review",
            page_count: 1,
            student_label: null,
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
        return { data: questions, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/dependency-graph") {
        const edges = options.edges ?? [];
        return {
          data: {
            id: "graph-1",
            test_id: DEFAULT_TEST_ID,
            status: "confirmed",
            version: 1,
            question_ids: questions.map((q) => q.id),
            edges,
            layers: [questions.map((q) => q.id)],
            unresolved: [],
            confirmed_at: "2026-01-01T00:00:00Z",
          },
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/submissions/{submission_id}/jobs") {
        const sequence = options.jobsSequence;
        if (sequence != null && sequence.length > 0) {
          const index = Math.min(jobsRead, sequence.length - 1);
          jobsRead += 1;
          // A fresh array each read, like a real HTTP response: reusing the
          // same reference would make React skip the re-render and stop the
          // screen's polling.
          return {
            data: [...(sequence[index] ?? [])],
            response: new Response(),
            error: undefined,
          };
        }
        return {
          data: [...jobs],
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/submissions/{submission_id}/pages") {
        return {
          data: {
            page_count: pages.length,
            pages: pages.map((page, index) => ({
              page_index: index,
              displayed_width: page.displayed_width,
              displayed_height: page.displayed_height,
              rotation: 0,
            })),
          },
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/submissions/{submission_id}/pages/{page_index}/image") {
        if (options.pageImageFails === true) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: { message: "image unavailable" },
          };
        }
        const blob = new Blob([new Uint8Array([137, 80, 78, 71])], {
          type: "image/png",
        });
        return { data: blob, response: new Response(), error: undefined };
      }
      if (
        path ===
        "/submissions/{submission_id}/questions/{question_id}/recognitions"
      ) {
        await questionDataGate.promise;
        return {
          data: recognitions,
          response: new Response(),
          error: undefined,
        };
      }
      if (
        path === "/submissions/{submission_id}/questions/{question_id}/grades"
      ) {
        await questionDataGate.promise;
        return { data: grades, response: new Response(), error: undefined };
      }
      if (
        path ===
        "/submissions/{submission_id}/questions/{question_id}/annotations"
      ) {
        await questionDataGate.promise;
        return {
          data: annotations,
          response: new Response(),
          error: undefined,
        };
      }
      if (
        path === "/submissions/{submission_id}/questions/{question_id}/reviews"
      ) {
        await questionDataGate.promise;
        return { data: reviews, response: new Response(), error: undefined };
      }
      if (
        path ===
        "/submissions/{submission_id}/questions/{question_id}/answer-image"
      ) {
        await questionDataGate.promise;
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
    POST: vi.fn(async () => ({
      data: {},
      response: new Response(),
      error: undefined,
    })),
    PUT: vi.fn(),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
    use: vi.fn(),
    eject: vi.fn(),
  } as unknown as SidecarClient;

  return {
    client,
    handle: {
      releaseInitialLoad: initialLoadGate.release,
      releaseQuestionData: questionDataGate.release,
    },
  };
}

export function renderPdfReview(
  options: PdfReviewHarnessOptions = {},
): RenderResult & { harness: PdfReviewHarnessHandle; client: SidecarClient } {
  const testId = options.testId ?? DEFAULT_TEST_ID;
  const submissionId = options.submissionId ?? DEFAULT_SUBMISSION_ID;
  const questionQuery =
    options.questionId != null
      ? `?question=${encodeURIComponent(options.questionId)}`
      : "";
  const location = `/tests/${testId}/submissions/${submissionId}/review${questionQuery}`;
  const { client, handle } = createPdfReviewClient(options);

  const view = render(
    <ThemeProvider>
      <SidecarApiProvider client={client}>
        <RouterProvider initialStack={[location]}>
          <PdfReviewPage />
        </RouterProvider>
      </SidecarApiProvider>
    </ThemeProvider>,
  );
  return Object.assign(view, { harness: handle, client });
}
