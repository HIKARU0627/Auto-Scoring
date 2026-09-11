import type { SidecarClient } from "./client.js";
import type { components } from "./generated/schema.js";
import {
  AnswerAreaDataError,
  loadAnswerAreaEditorData,
  type AnswerAreaEditorData,
} from "./answer-area-data.js";

export type TestResponse = components["schemas"]["TestResponse"];
export type ProfileResponse = components["schemas"]["ProfileResponse"];
export type CriteriaResponse = components["schemas"]["CriteriaResponse"];
export type CriteriaQuestionModel =
  components["schemas"]["CriteriaQuestionModel"];
export type CriteriaEstimateResponse =
  components["schemas"]["CriteriaEstimateResponse"];
export type AnswerLayoutResponse =
  components["schemas"]["AnswerLayoutResponse"];
export type DependencyGraphResponse =
  components["schemas"]["DependencyGraphResponse"];
export type DependencyEdgeModel = components["schemas"]["DependencyEdgeModel"];
export type QuestionResponse = components["schemas"]["QuestionResponse"];
export type CompleteRegistrationResponse =
  components["schemas"]["CompleteRegistrationResponse"];

export class TestRegistrationDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TestRegistrationDataError";
  }
}

export interface TestSettingsSnapshot {
  readonly test: TestResponse;
  readonly profile: ProfileResponse | null;
  readonly criteria: CriteriaResponse | null;
  readonly dependencyGraph: DependencyGraphResponse | null;
  readonly answerLayout: AnswerLayoutResponse | null;
  readonly questionNumbers: readonly string[];
  readonly editor: AnswerAreaEditorData;
}

function readErrorMessage(fallback: string, body: unknown): string {
  if (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof (body as { detail: unknown }).detail === "string"
  ) {
    return (body as { detail: string }).detail;
  }
  return fallback;
}

async function getOptional<T>(
  result: { data?: T; error?: unknown; response: Response },
  notFoundOk: boolean,
  fallbackMessage: string,
): Promise<T | null> {
  if (result.error === undefined) {
    return result.data as T;
  }
  if (notFoundOk && result.response.status === 404) {
    return null;
  }
  throw new TestRegistrationDataError(
    readErrorMessage(fallbackMessage, result.error),
  );
}

export async function loadTestSettingsSnapshot(
  client: SidecarClient,
  testId: string,
): Promise<TestSettingsSnapshot> {
  const [testResult, profileResult, criteriaResult, graphResult, editor] =
    await Promise.all([
      client.GET("/tests/{test_id}", {
        params: { path: { test_id: testId } },
      }),
      client.GET("/tests/{test_id}/profile", {
        params: { path: { test_id: testId } },
      }),
      client.GET("/tests/{test_id}/criteria", {
        params: { path: { test_id: testId } },
      }),
      client.GET("/tests/{test_id}/dependency-graph", {
        params: { path: { test_id: testId } },
      }),
      loadAnswerAreaEditorData(client, testId),
    ]);

  if (testResult.error !== undefined) {
    throw new TestRegistrationDataError("テストを取得できません");
  }

  const profile = await getOptional(
    profileResult,
    true,
    "プロファイルを取得できません",
  );
  const criteria = await getOptional(
    criteriaResult,
    true,
    "配点と採点基準を取得できません",
  );
  const dependencyGraph = await getOptional(
    graphResult,
    true,
    "設問依存関係グラフを取得できません",
  );

  const questionsResult = await client.GET("/tests/{test_id}/questions", {
    params: { path: { test_id: testId } },
  });
  if (questionsResult.error !== undefined) {
    throw new TestRegistrationDataError("設問一覧を取得できません");
  }

  return {
    test: testResult.data,
    profile,
    criteria,
    dependencyGraph,
    answerLayout: editor.layout,
    questionNumbers: questionsResult.data.map((question) => question.number),
    editor,
  };
}

export async function estimateCriteriaExtract(
  client: SidecarClient,
  testId: string,
): Promise<CriteriaEstimateResponse> {
  const result = await client.GET("/tests/{test_id}/criteria/estimate", {
    params: { path: { test_id: testId } },
  });
  if (result.error !== undefined) {
    throw new TestRegistrationDataError(
      readErrorMessage("見積りを取得できません", result.error),
    );
  }
  return result.data;
}

export async function extractCriteria(
  client: SidecarClient,
  testId: string,
): Promise<CriteriaResponse> {
  const result = await client.POST("/tests/{test_id}/criteria/extract", {
    params: { path: { test_id: testId } },
  });
  if (result.error !== undefined) {
    throw new TestRegistrationDataError(
      readErrorMessage("採点基準の抽出に失敗しました", result.error),
    );
  }
  return result.data;
}

export async function updateCriteria(
  client: SidecarClient,
  testId: string,
  input: {
    questions: readonly CriteriaQuestionModel[];
    declaredTotalPoints?: number | null;
  },
): Promise<CriteriaResponse> {
  const result = await client.PUT("/tests/{test_id}/criteria", {
    params: { path: { test_id: testId } },
    body: {
      questions: [...input.questions],
      declared_total_points: input.declaredTotalPoints ?? null,
    },
  });
  if (result.error !== undefined) {
    throw new TestRegistrationDataError(
      readErrorMessage("配点と採点基準を保存できません", result.error),
    );
  }
  return result.data;
}

export async function confirmCriteria(
  client: SidecarClient,
  testId: string,
  revision: number,
): Promise<CriteriaResponse> {
  const result = await client.POST("/tests/{test_id}/criteria/confirm", {
    params: { path: { test_id: testId } },
    body: { revision },
  });
  if (result.error !== undefined) {
    throw new TestRegistrationDataError(
      readErrorMessage("配点と採点基準を確定できません", result.error),
    );
  }
  return result.data;
}

export async function uploadAnswerLayout(
  testId: string,
  filePath: string,
): Promise<AnswerLayoutResponse> {
  const bridge = window.autoScoring;
  if (bridge === undefined) {
    throw new TestRegistrationDataError("答案ファイルを選べません");
  }
  const response = await bridge.sidecarMultipartUpload({
    method: "PUT",
    urlPath: `/tests/${encodeURIComponent(testId)}/answer-layout`,
    fileFields: [{ fieldName: "file", filePath }],
  });
  if (response.status !== 200) {
    throw new TestRegistrationDataError(
      readErrorMessage("答案を取り込めません", response.body),
    );
  }
  return response.body as AnswerLayoutResponse;
}

export async function detectAnswerAreas(
  client: SidecarClient,
  testId: string,
): Promise<ProfileResponse> {
  const result = await client.POST("/tests/{test_id}/answer-layout/detect", {
    params: { path: { test_id: testId } },
  });
  if (result.error !== undefined) {
    throw new TestRegistrationDataError(
      readErrorMessage("回答欄を検出できません", result.error),
    );
  }
  return result.data;
}

export async function updateProfile(
  client: SidecarClient,
  testId: string,
  regions: components["schemas"]["RegionModel"][],
): Promise<ProfileResponse> {
  const result = await client.PUT("/tests/{test_id}/profile", {
    params: { path: { test_id: testId } },
    body: { regions },
  });
  if (result.error !== undefined) {
    throw new TestRegistrationDataError(
      readErrorMessage("プロファイルを保存できません", result.error),
    );
  }
  return result.data;
}

export async function confirmProfile(
  client: SidecarClient,
  testId: string,
  revision: number,
): Promise<ProfileResponse> {
  const result = await client.POST("/tests/{test_id}/profile/confirm", {
    params: { path: { test_id: testId } },
    body: { revision },
  });
  if (result.error !== undefined) {
    throw new TestRegistrationDataError(
      readErrorMessage("プロファイルを確定できません", result.error),
    );
  }
  return result.data;
}

export async function analyzeDependencyGraph(
  client: SidecarClient,
  testId: string,
  overrides: components["schemas"]["QuestionTextOverride"][] = [],
): Promise<DependencyGraphResponse> {
  const result = await client.POST(
    "/tests/{test_id}/dependency-graph/analyze",
    {
      params: { path: { test_id: testId } },
      body: { overrides },
    },
  );
  if (result.error !== undefined) {
    throw new TestRegistrationDataError(
      readErrorMessage("依存関係を分析できません", result.error),
    );
  }
  return result.data;
}

export async function confirmDependencyGraph(
  client: SidecarClient,
  testId: string,
  input: { version: number; edges: readonly DependencyEdgeModel[] },
): Promise<DependencyGraphResponse> {
  const result = await client.POST(
    "/tests/{test_id}/dependency-graph/confirm",
    {
      params: { path: { test_id: testId } },
      body: {
        version: input.version,
        edges: [...input.edges],
      },
    },
  );
  if (result.error !== undefined) {
    throw new TestRegistrationDataError(
      readErrorMessage("依存関係グラフを確定できません", result.error),
    );
  }
  return result.data;
}

export async function completeRegistration(
  client: SidecarClient,
  testId: string,
): Promise<CompleteRegistrationResponse> {
  const result = await client.POST("/tests/{test_id}/complete-registration", {
    params: { path: { test_id: testId } },
  });
  if (result.error !== undefined) {
    throw new TestRegistrationDataError(
      readErrorMessage("登録を完了できません", result.error),
    );
  }
  return result.data;
}

export async function reloadAnswerAreaEditor(
  client: SidecarClient,
  testId: string,
): Promise<AnswerAreaEditorData> {
  try {
    return await loadAnswerAreaEditorData(client, testId);
  } catch (error) {
    if (error instanceof AnswerAreaDataError) {
      throw new TestRegistrationDataError(error.message);
    }
    throw error;
  }
}

export function buildQuestionTextOverrides(
  testId: string,
  profile: ProfileResponse | null,
): components["schemas"]["QuestionTextOverride"][] {
  if (profile === null) {
    return [];
  }
  return profile.regions
    .filter((region) => region.kind === "question")
    .map((region) => ({
      question_id: `${testId}:${region.label}`,
      prompt_text: region.text ?? "",
    }));
}

export function emptyCriteriaQuestion(index: number): CriteriaQuestionModel {
  return {
    number: `問${index + 1}`,
    points: null,
    model_answer: null,
    criteria: [
      {
        description: "要点に触れている",
        kind: "add",
        points: 10,
      },
    ],
    source_pages: [],
    note: null,
  };
}

export function manualAnswerAreaRegion(input: {
  regionId: string;
  label: string;
}): components["schemas"]["RegionModel"] {
  return {
    region_id: input.regionId,
    kind: "answer_area",
    page_index: 0,
    label: input.label,
    confirmed: false,
    text: null,
    bbox: { x0: 0.1, y0: 0.25, x1: 0.9, y1: 0.55 },
  };
}
