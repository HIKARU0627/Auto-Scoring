import type { SidecarClient } from "../api/client.js";
import type { components } from "../api/generated/schema.js";
import type { PageImageState } from "./page-image.js";
import { geometryToImagePixelSize } from "./normalized-coordinates.js";

export type SubmissionResponse = components["schemas"]["SubmissionResponse"];
export type QuestionResponse = components["schemas"]["QuestionResponse"];
export type JobResponse = components["schemas"]["JobResponse"];
export type GradeResultResponse = components["schemas"]["GradeResultResponse"];
export type ReviewResponse = components["schemas"]["ReviewResponse"];
export type AnnotationResponse = components["schemas"]["AnnotationResponse"];
export type RecognitionResponse = components["schemas"]["RecognitionResponse"];
export type DependencyGraphResponse =
  components["schemas"]["DependencyGraphResponse"];
export type PageGeometryResponse =
  components["schemas"]["PageGeometryResponse"];

export class PdfReviewDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PdfReviewDataError";
  }
}

const DEFAULT_IMAGE_SCALE = 2;

export interface SubmissionPageState {
  readonly geometry: PageGeometryResponse;
  readonly image: PageImageState;
}

export interface QuestionReviewData {
  readonly recognitions: readonly RecognitionResponse[];
  readonly grades: readonly GradeResultResponse[];
  readonly annotations: readonly AnnotationResponse[];
  readonly reviews: readonly ReviewResponse[];
}

export async function loadSubmission(
  client: SidecarClient,
  submissionId: string,
): Promise<SubmissionResponse> {
  const result = await client.GET("/submissions/{submission_id}", {
    params: { path: { submission_id: submissionId } },
  });
  if (result.error !== undefined) {
    throw new PdfReviewDataError("答案を取得できません");
  }
  return result.data;
}

export async function loadQuestions(
  client: SidecarClient,
  testId: string,
): Promise<QuestionResponse[]> {
  const result = await client.GET("/tests/{test_id}/questions", {
    params: { path: { test_id: testId } },
  });
  if (result.error !== undefined) {
    throw new PdfReviewDataError("設問を取得できません");
  }
  return result.data;
}

export async function loadDependencyGraph(
  client: SidecarClient,
  testId: string,
): Promise<DependencyGraphResponse> {
  const result = await client.GET("/tests/{test_id}/dependency-graph", {
    params: { path: { test_id: testId } },
  });
  if (result.error !== undefined) {
    throw new PdfReviewDataError("依存関係を取得できません");
  }
  return result.data;
}

export async function loadJobs(
  client: SidecarClient,
  submissionId: string,
): Promise<JobResponse[]> {
  const result = await client.GET("/submissions/{submission_id}/jobs", {
    params: { path: { submission_id: submissionId } },
  });
  if (result.error !== undefined) {
    throw new PdfReviewDataError("ジョブを取得できません");
  }
  return result.data;
}

export async function loadQuestionReviewData(
  client: SidecarClient,
  submissionId: string,
  questionId: string,
): Promise<QuestionReviewData> {
  const [recognitions, grades, annotations, reviews] = await Promise.all([
    client.GET(
      "/submissions/{submission_id}/questions/{question_id}/recognitions",
      {
        params: {
          path: { submission_id: submissionId, question_id: questionId },
        },
      },
    ),
    client.GET("/submissions/{submission_id}/questions/{question_id}/grades", {
      params: {
        path: { submission_id: submissionId, question_id: questionId },
      },
    }),
    client.GET(
      "/submissions/{submission_id}/questions/{question_id}/annotations",
      {
        params: {
          path: { submission_id: submissionId, question_id: questionId },
        },
      },
    ),
    client.GET("/submissions/{submission_id}/questions/{question_id}/reviews", {
      params: {
        path: { submission_id: submissionId, question_id: questionId },
      },
    }),
  ]);

  if (recognitions.error !== undefined) {
    throw new PdfReviewDataError("認識結果を取得できません");
  }
  if (grades.error !== undefined) {
    throw new PdfReviewDataError("採点結果を取得できません");
  }
  if (annotations.error !== undefined) {
    throw new PdfReviewDataError("注釈を取得できません");
  }
  if (reviews.error !== undefined) {
    throw new PdfReviewDataError("レビュー履歴を取得できません");
  }

  return {
    recognitions: recognitions.data,
    grades: grades.data,
    annotations: annotations.data,
    reviews: reviews.data,
  };
}

async function loadPageImage(
  client: SidecarClient,
  submissionId: string,
  pageIndex: number,
  geometry: PageGeometryResponse,
): Promise<PageImageState> {
  const result = await client.GET(
    "/submissions/{submission_id}/pages/{page_index}/image",
    {
      params: {
        path: { submission_id: submissionId, page_index: pageIndex },
        query: { scale: DEFAULT_IMAGE_SCALE },
      },
      parseAs: "blob",
    },
  );
  if (result.error !== undefined) {
    return { objectUrl: null, pixelWidth: null, pixelHeight: null };
  }
  const blob = result.data as Blob;
  const objectUrl = URL.createObjectURL(blob);
  const expected = geometryToImagePixelSize(
    geometry.displayed_width,
    geometry.displayed_height,
    DEFAULT_IMAGE_SCALE,
  );
  return {
    objectUrl,
    pixelWidth: expected.width,
    pixelHeight: expected.height,
  };
}

export async function loadSubmissionPages(
  client: SidecarClient,
  submissionId: string,
): Promise<readonly SubmissionPageState[]> {
  const pagesResult = await client.GET("/submissions/{submission_id}/pages", {
    params: { path: { submission_id: submissionId } },
  });
  if (pagesResult.error !== undefined) {
    throw new PdfReviewDataError("ページ情報を取得できません");
  }
  const pages: SubmissionPageState[] = [];
  for (let i = 0; i < pagesResult.data.pages.length; i += 1) {
    const geometry = pagesResult.data.pages[i];
    if (geometry == null) {
      continue;
    }
    const image = await loadPageImage(client, submissionId, i, geometry);
    pages.push({ geometry, image });
  }
  return pages;
}

export async function loadAnswerImageUrl(
  client: SidecarClient,
  submissionId: string,
  questionId: string,
): Promise<string | null> {
  const result = await client.GET(
    "/submissions/{submission_id}/questions/{question_id}/answer-image",
    {
      params: {
        path: { submission_id: submissionId, question_id: questionId },
      },
      parseAs: "blob",
    },
  );
  if (result.error !== undefined) {
    return null;
  }
  return URL.createObjectURL(result.data as Blob);
}
