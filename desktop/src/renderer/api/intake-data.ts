import type { ScannedEntry } from "../../shared/folder-scan.js";
import {
  materialRoleWireValue,
  PDF_CONTENT_TYPE,
  type SidecarConnectionInfo,
} from "../../shared/sidecar-upload.js";
import type { SidecarClient } from "./client.js";
import type { components } from "./generated/schema.js";
import { gradingKickoffFailureFromStatus } from "../core/grading-kickoff.js";
import type { MaterialRole } from "../core/material-role-labels.js";
import {
  effectiveRole,
  includedFiles,
  IntakeTargetKind,
  intakeFileName,
  type IntakeFileState,
  type IntakeGroupState,
  type IntakeReviewState,
} from "../core/intake-review.js";

export type IntakeTemplateModel = components["schemas"]["IntakeTemplateModel"];
export type IntakePlanResponse = components["schemas"]["IntakePlanResponse"];
export type TestSummary = components["schemas"]["TestSummary"];
export type TestResponse = components["schemas"]["TestResponse"];
export type SubmissionResponse = components["schemas"]["SubmissionResponse"];

export class IntakeDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "IntakeDataError";
  }
}

export interface IntakeBridge {
  chooseFolder(): Promise<string | null>;
  scanFolder(directoryPath: string): Promise<{
    name: string;
    entries: readonly ScannedEntry[];
  }>;
  sidecarMultipartUpload(request: {
    connection: SidecarConnectionInfo;
    method: "POST" | "PUT";
    urlPath: string;
    fileFields: readonly {
      fieldName: string;
      filePath: string;
      contentType?: string;
    }[];
    formFields?: Readonly<Record<string, string | readonly string[]>>;
  }): Promise<{ status: number; body: unknown }>;
}

export function intakeBridgeFromWindow(): IntakeBridge {
  return window.autoScoring;
}

export async function loadIntakeTemplates(
  client: SidecarClient,
): Promise<IntakeTemplateModel[]> {
  const response = await client.GET("/intake-templates");
  if (response.error !== undefined) {
    throw new IntakeDataError("取込の型を取得できません");
  }
  return response.data;
}

export async function loadIntakeCost(
  client: SidecarClient,
): Promise<number | null> {
  const response = await client.GET("/intake-cost");
  if (response.error !== undefined) {
    throw new IntakeDataError("単価を取得できません");
  }
  return response.data.classification_unit_cost ?? null;
}

export async function loadClassificationAvailability(
  client: SidecarClient,
): Promise<components["schemas"]["ClassificationAvailabilityResponse"]> {
  const response = await client.GET("/intake/classification-availability");
  if (response.error !== undefined) {
    throw new IntakeDataError("AI判定の利用可否を取得できません");
  }
  return response.data;
}

export async function listTests(client: SidecarClient): Promise<TestSummary[]> {
  const response = await client.GET("/tests");
  if (response.error !== undefined) {
    throw new IntakeDataError("登録済みテストを取得できません");
  }
  return response.data;
}

export async function planIntake(
  client: SidecarClient,
  input: {
    templateId: string;
    rootName: string;
    entries: readonly ScannedEntry[];
  },
): Promise<IntakePlanResponse> {
  const response = await client.POST("/intake/plan", {
    body: {
      template_id: input.templateId,
      root_name: input.rootName,
      files: input.entries.map((entry) => ({
        relative_path: entry.relativePath,
        size_bytes: entry.sizeBytes,
        sha256: entry.sha256,
      })),
    },
  });
  if (response.error !== undefined) {
    throw new IntakeDataError("取込プランを作成できません");
  }
  return response.data;
}

export async function classifyMaterial(
  bridge: IntakeBridge,
  connection: SidecarConnectionInfo,
  filePath: string,
): Promise<components["schemas"]["RoleProposalResponse"]> {
  const response = await bridge.sidecarMultipartUpload({
    connection,
    method: "POST",
    urlPath: "/intake/classify",
    fileFields: [{ fieldName: "file", filePath }],
  });
  if (response.status >= 400) {
    throw new IntakeDataError("AIによる役割判定に失敗しました");
  }
  return response.body as components["schemas"]["RoleProposalResponse"];
}

export async function attributeAnswer(
  bridge: IntakeBridge,
  connection: SidecarConnectionInfo,
  input: {
    filePath: string;
    candidates: readonly { id: string; label: string }[];
  },
): Promise<components["schemas"]["AttributionProposalResponse"]> {
  const response = await bridge.sidecarMultipartUpload({
    connection,
    method: "POST",
    urlPath: "/intake/attribute",
    fileFields: [{ fieldName: "file", filePath: input.filePath }],
    formFields: {
      candidate_ids: input.candidates.map((candidate) => candidate.id),
      candidate_labels: input.candidates.map((candidate) => candidate.label),
    },
  });
  if (response.status >= 400) {
    throw new IntakeDataError("AIによる答案振り分けに失敗しました");
  }
  return response.body as components["schemas"]["AttributionProposalResponse"];
}

function isDuplicateSubmission(body: unknown): boolean {
  if (typeof body !== "object" || body === null) {
    return false;
  }
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail !== "object" || detail === null) {
    return false;
  }
  return "existing_submission_id" in detail;
}

export async function createSubmission(
  bridge: IntakeBridge,
  connection: SidecarConnectionInfo,
  testId: string,
  filePath: string,
): Promise<SubmissionResponse | "duplicate"> {
  const response = await bridge.sidecarMultipartUpload({
    connection,
    method: "POST",
    urlPath: `/tests/${testId}/submissions`,
    fileFields: [
      { fieldName: "file", filePath, contentType: PDF_CONTENT_TYPE },
    ],
  });
  if (response.status === 409 && isDuplicateSubmission(response.body)) {
    return "duplicate";
  }
  if (response.status >= 400) {
    throw new IntakeDataError("答案の取込に失敗しました");
  }
  return response.body as SubmissionResponse;
}

export async function createTest(
  bridge: IntakeBridge,
  connection: SidecarConnectionInfo,
  input: {
    name: string;
    criteriaPath: string;
    materials: readonly { role: MaterialRole; path: string }[];
  },
): Promise<TestResponse> {
  const extras = input.materials.filter(
    (material) => material.path !== input.criteriaPath,
  );
  const response = await bridge.sidecarMultipartUpload({
    connection,
    method: "POST",
    urlPath: "/tests",
    fileFields: [
      { fieldName: "criteria", filePath: input.criteriaPath },
      ...extras.map((material) => ({
        fieldName: "materials",
        filePath: material.path,
        contentType: PDF_CONTENT_TYPE,
      })),
    ],
    formFields: {
      name: input.name,
      material_roles: extras.map((material) =>
        materialRoleWireValue(material.role),
      ),
    },
  });
  if (response.status >= 400) {
    throw new IntakeDataError("テストの登録に失敗しました");
  }
  return response.body as TestResponse;
}

export async function addMaterials(
  bridge: IntakeBridge,
  connection: SidecarConnectionInfo,
  testId: string,
  materials: readonly { role: MaterialRole; path: string }[],
): Promise<number> {
  if (materials.length === 0) {
    return 0;
  }
  const response = await bridge.sidecarMultipartUpload({
    connection,
    method: "POST",
    urlPath: `/tests/${testId}/materials`,
    fileFields: materials.map((material) => ({
      fieldName: "materials",
      filePath: material.path,
      contentType: PDF_CONTENT_TYPE,
    })),
    formFields: {
      material_roles: materials.map((material) =>
        materialRoleWireValue(material.role),
      ),
    },
  });
  if (response.status >= 400) {
    throw new IntakeDataError("資料の追加に失敗しました");
  }
  const body = response.body;
  return Array.isArray(body) ? body.length : materials.length;
}

export async function startGrading(
  client: SidecarClient,
  submissionId: string,
): Promise<void> {
  const response = await client.POST("/submissions/{submission_id}/jobs", {
    params: { path: { submission_id: submissionId } },
  });
  if (response.error !== undefined) {
    throw new IntakeDataError(
      gradingKickoffFailureFromStatus(response.response.status).message,
    );
  }
}

export interface ImportOutcome {
  readonly groupKey: string;
  readonly name: string;
  readonly testId: string | null;
  readonly createdTest: boolean;
  readonly materialCount: number;
  readonly submissionCount: number;
  readonly duplicateCount: number;
  readonly gradingStartedCount: number;
  readonly gradingFailure: string | null;
  readonly error: string | null;
  readonly failedFiles: readonly string[];
}

function importedAnything(outcome: ImportOutcome): boolean {
  return (
    outcome.materialCount > 0 ||
    outcome.submissionCount > 0 ||
    outcome.duplicateCount > 0
  );
}

async function importAnswers(
  deps: {
    bridge: IntakeBridge;
    connection: SidecarConnectionInfo;
    client: SidecarClient;
  },
  testId: string,
  answers: readonly IntakeFileState[],
): Promise<{
  imported: number;
  duplicates: number;
  gradingStarted: number;
  gradingFailure: string | null;
  failure: string | null;
  failedFiles: string[];
}> {
  let imported = 0;
  let duplicates = 0;
  let gradingStarted = 0;
  let gradingFailure: string | null = null;
  let failure: string | null = null;
  const failedFiles: string[] = [];

  for (const answer of answers) {
    try {
      const submission = await createSubmission(
        deps.bridge,
        deps.connection,
        testId,
        answer.absolutePath,
      );
      if (submission === "duplicate") {
        duplicates++;
        continue;
      }
      imported++;
      if (submission.state !== "ai_processed") {
        continue;
      }
      try {
        await startGrading(deps.client, submission.id);
        gradingStarted++;
      } catch (error) {
        gradingFailure ??=
          error instanceof IntakeDataError
            ? error.message
            : "AI採点を開始できませんでした";
      }
    } catch (error) {
      failure ??=
        error instanceof IntakeDataError
          ? error.message
          : "答案の取込に失敗しました";
      failedFiles.push(intakeFileName(answer));
    }
  }

  return {
    imported,
    duplicates,
    gradingStarted,
    gradingFailure,
    failure,
    failedFiles,
  };
}

async function importRoutedAnswers(
  deps: {
    bridge: IntakeBridge;
    connection: SidecarConnectionInfo;
    client: SidecarClient;
  },
  group: IntakeGroupState,
  answers: readonly IntakeFileState[],
): Promise<ImportOutcome> {
  let imported = 0;
  let duplicates = 0;
  let gradingStarted = 0;
  let gradingFailure: string | null = null;
  let failure: string | null = null;
  const failedFiles: string[] = [];

  for (const answer of answers) {
    const testId = answer.answerTestId;
    if (testId === null) {
      continue;
    }
    const result = await importAnswers(deps, testId, [answer]);
    imported += result.imported;
    duplicates += result.duplicates;
    gradingStarted += result.gradingStarted;
    gradingFailure ??= result.gradingFailure;
    failure ??= result.failure;
    failedFiles.push(...result.failedFiles);
  }

  return {
    groupKey: group.key,
    name: group.name,
    testId: null,
    createdTest: false,
    materialCount: 0,
    submissionCount: imported,
    duplicateCount: duplicates,
    gradingStartedCount: gradingStarted,
    gradingFailure,
    error: failure,
    failedFiles,
  };
}

async function importGroup(
  deps: {
    bridge: IntakeBridge;
    connection: SidecarConnectionInfo;
    client: SidecarClient;
  },
  group: IntakeGroupState,
): Promise<ImportOutcome> {
  const included = includedFiles(group);
  const answers = included.filter(
    (file) => effectiveRole(file) === "student_answer",
  );
  const materials = included.flatMap((file) => {
    const role = effectiveRole(file);
    if (role === null || role === "student_answer" || role === "ignore") {
      return [];
    }
    return [{ role, path: file.absolutePath }];
  });

  if (group.targetKind === IntakeTargetKind.perAnswer) {
    return await importRoutedAnswers(deps, group, answers);
  }

  let testId = group.targetTestId;
  let materialCount = 0;
  try {
    if (group.targetKind === IntakeTargetKind.create) {
      const criteria = included.find(
        (file) => effectiveRole(file) === "grading_criteria",
      );
      if (criteria === undefined) {
        return {
          groupKey: group.key,
          name: group.name,
          testId: null,
          createdTest: true,
          materialCount: 0,
          submissionCount: 0,
          duplicateCount: 0,
          gradingStartedCount: 0,
          gradingFailure: null,
          error: "採点基準のファイルが選ばれていません。",
          failedFiles: [],
        };
      }
      const extras = materials.filter(
        (material) => material.path !== criteria.absolutePath,
      );
      const test = await createTest(deps.bridge, deps.connection, {
        name: group.name.trim(),
        criteriaPath: criteria.absolutePath,
        materials: extras,
      });
      testId = test.id;
      materialCount = extras.length + 1;
    } else if (materials.length > 0 && testId !== null) {
      materialCount = await addMaterials(
        deps.bridge,
        deps.connection,
        testId,
        materials,
      );
    }

    if (testId === null) {
      return {
        groupKey: group.key,
        name: group.name,
        testId: null,
        createdTest: false,
        materialCount: 0,
        submissionCount: 0,
        duplicateCount: 0,
        gradingStartedCount: 0,
        gradingFailure: null,
        error: "取込先のテストが選ばれていません。",
        failedFiles: [],
      };
    }

    const answersResult = await importAnswers(deps, testId, answers);
    return {
      groupKey: group.key,
      name: group.name,
      testId,
      createdTest: group.targetKind === IntakeTargetKind.create,
      materialCount,
      submissionCount: answersResult.imported,
      duplicateCount: answersResult.duplicates,
      gradingStartedCount: answersResult.gradingStarted,
      gradingFailure: answersResult.gradingFailure,
      error: answersResult.failure,
      failedFiles: answersResult.failedFiles,
    };
  } catch (error) {
    return {
      groupKey: group.key,
      name: group.name,
      testId: testId ?? null,
      createdTest: group.targetKind === IntakeTargetKind.create,
      materialCount,
      submissionCount: 0,
      duplicateCount: 0,
      gradingStartedCount: 0,
      gradingFailure: null,
      error:
        error instanceof IntakeDataError ? error.message : "取込に失敗しました",
      failedFiles: [],
    };
  }
}

export async function importReview(
  deps: {
    bridge: IntakeBridge;
    connection: SidecarConnectionInfo;
    client: SidecarClient;
  },
  review: IntakeReviewState,
): Promise<readonly ImportOutcome[]> {
  const outcomes: ImportOutcome[] = [];
  for (const group of review.groups) {
    if (includedFiles(group).length === 0) {
      continue;
    }
    outcomes.push(await importGroup(deps, group));
  }
  return outcomes;
}

export { importedAnything, materialRoleWireValue, PDF_CONTENT_TYPE };
