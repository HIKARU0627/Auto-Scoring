import type { ScannedEntry } from "../../shared/folder-scan.js";
import {
  materialRoleWireValue,
  PDF_CONTENT_TYPE,
} from "../../shared/sidecar-upload.js";
import type { SidecarClient } from "../api/client.js";
import type { components } from "../api/generated/schema.js";
import {
  submissionImportFailureRequirement,
  type SubmissionImportFailureKind,
} from "./action-requirements.js";
import { gradingKickoffFailureFromStatus } from "./grading-kickoff.js";
import type { MaterialRole } from "./material-role-labels.js";
import {
  effectiveRole,
  includedFiles,
  IntakeTargetKind,
  intakeFileName,
  targetTestAcceptsAnswers,
  type IntakeFileState,
  type IntakeGroupState,
  type IntakeReviewState,
} from "./intake-review.js";

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

/**
 * 答案 1 件の取込が失敗した理由 (Issue #306)。`status` と `detail` を捨てずに
 * 呼び出し元へ渡し、画面は `core/action-requirements.ts` の文言で理由を出す。
 */
export class SubmissionIntakeError extends IntakeDataError {
  readonly status: number;
  readonly kind: SubmissionImportFailureKind;
  readonly detail: string | null;

  constructor(input: {
    status: number;
    kind: SubmissionImportFailureKind;
    detail: string | null;
  }) {
    super(submissionImportFailureRequirement(input.kind).message);
    this.name = "SubmissionIntakeError";
    this.status = input.status;
    this.kind = input.kind;
    this.detail = input.detail;
  }
}

export interface IntakeBridge {
  chooseFolder(): Promise<string | null>;
  scanFolder(directoryPath: string): Promise<{
    name: string;
    entries: readonly ScannedEntry[];
  }>;
  sidecarMultipartUpload(request: {
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

/**
 * 登録済みテストを**状態つき**で取得する (Issue #306)。答案を受け付けるのは
 * `ready` だけなので、取込の段分けはこの `status` から機械的に決める。`GET /tests`
 * は `ready` しか返さないため、登録途中のテストも再利用できる `GET /test-registrations`
 * を使う。
 */
export async function listTests(
  client: SidecarClient,
): Promise<TestResponse[]> {
  const response = await client.GET("/test-registrations");
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
  filePath: string,
): Promise<components["schemas"]["RoleProposalResponse"]> {
  const response = await bridge.sidecarMultipartUpload({
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
  input: {
    filePath: string;
    candidates: readonly { id: string; label: string }[];
  },
): Promise<components["schemas"]["AttributionProposalResponse"]> {
  const response = await bridge.sidecarMultipartUpload({
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

function detailOf(body: unknown): unknown {
  if (typeof body !== "object" || body === null) {
    return undefined;
  }
  return (body as { detail?: unknown }).detail;
}

function isDuplicateSubmission(body: unknown): boolean {
  const detail = detailOf(body);
  return (
    typeof detail === "object" &&
    detail !== null &&
    "existing_submission_id" in detail
  );
}

function isRetryConflictSubmission(body: unknown): boolean {
  const detail = detailOf(body);
  return (
    typeof detail === "object" && detail !== null && "submission_id" in detail
  );
}

/** バックエンドの `detail`（文字列か `{message}`）から人が読める 1 行を取り出す。 */
function submissionDetailText(body: unknown): string | null {
  const detail = detailOf(body);
  if (typeof detail === "string") {
    return detail.length > 0 ? detail : null;
  }
  if (typeof detail === "object" && detail !== null) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.length > 0) {
      return message;
    }
  }
  return null;
}

/**
 * 失敗の種類を HTTP status と `detail` の形から決める。文言は付けない
 * （それは `core/action-requirements.ts` の仕事）。
 *
 * - 409 + `existing_submission_id` は重複なので `createSubmission` が先に握る。
 * - 409 + `submission_id` は再取込の競合。
 * - それ以外の 409 は `TestNotReadyError`（登録未完了）。
 * - 5xx は再試行できる一時障害、その他の 4xx は入力そのものの拒否。
 */
function submissionFailureKind(
  status: number,
  body: unknown,
): SubmissionImportFailureKind {
  if (status === 409) {
    return isRetryConflictSubmission(body) ? "retry-conflict" : "not-ready";
  }
  if (status >= 500) {
    return "server";
  }
  return "rejected";
}

export async function createSubmission(
  bridge: IntakeBridge,
  testId: string,
  filePath: string,
): Promise<SubmissionResponse | "duplicate"> {
  const response = await bridge.sidecarMultipartUpload({
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
    throw new SubmissionIntakeError({
      status: response.status,
      kind: submissionFailureKind(response.status, response.body),
      detail: submissionDetailText(response.body),
    });
  }
  return response.body as SubmissionResponse;
}

export async function createTest(
  bridge: IntakeBridge,
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
  testId: string,
  materials: readonly { role: MaterialRole; path: string }[],
): Promise<number> {
  if (materials.length === 0) {
    return 0;
  }
  const response = await bridge.sidecarMultipartUpload({
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
  /** 取込先テストの status（`draft` / `ready`）。未確定なら `null`。 */
  readonly testStatus: string | null;
  readonly createdTest: boolean;
  readonly materialCount: number;
  readonly submissionCount: number;
  readonly duplicateCount: number;
  /**
   * 登録が済んでいないため、この取込では上げなかった答案の件数 (Issue #306 第 1 段)。
   * 登録完了後に同じフォルダをもう一度取り込むと 0 になる。
   */
  readonly answersDeferred: number;
  readonly gradingStartedCount: number;
  readonly gradingFailure: string | null;
  readonly error: string | null;
  readonly failedFiles: readonly string[];
}

/** 取込に必要な外部依存。`testStatusById` は perAnswer の振り分け先の段判定に使う。 */
export interface ImportDeps {
  readonly bridge: IntakeBridge;
  readonly client: SidecarClient;
  readonly testStatusById?: ReadonlyMap<string, string>;
}

function importedAnything(outcome: ImportOutcome): boolean {
  return (
    outcome.materialCount > 0 ||
    outcome.submissionCount > 0 ||
    outcome.duplicateCount > 0
  );
}

async function importAnswers(
  deps: ImportDeps,
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
          : submissionImportFailureRequirement("server").message;
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
  deps: ImportDeps,
  group: IntakeGroupState,
  answers: readonly IntakeFileState[],
): Promise<ImportOutcome> {
  let imported = 0;
  let duplicates = 0;
  let deferred = 0;
  let gradingStarted = 0;
  let gradingFailure: string | null = null;
  let failure: string | null = null;
  const failedFiles: string[] = [];

  for (const answer of answers) {
    const testId = answer.answerTestId;
    if (testId === null) {
      continue;
    }
    // 段は振り分け先テストの status から機械的に決める (Issue #306 案 A)。
    const status = deps.testStatusById?.get(testId) ?? null;
    if (!targetTestAcceptsAnswers(status)) {
      deferred++;
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
    testStatus: null,
    createdTest: false,
    materialCount: 0,
    submissionCount: imported,
    duplicateCount: duplicates,
    answersDeferred: deferred,
    gradingStartedCount: gradingStarted,
    gradingFailure,
    error: failure,
    failedFiles,
  };
}

async function importGroup(
  deps: ImportDeps,
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

  const createdTest = group.targetKind === IntakeTargetKind.create;
  let testId = group.targetTestId;
  // 既存テストを再利用するときの status は、画面の一時状態ではなく
  // 読み込み済みの `TestResponse.status` から渡される (Issue #306)。
  let testStatus = group.targetTestStatus;
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
          testStatus: null,
          createdTest: true,
          materialCount: 0,
          submissionCount: 0,
          duplicateCount: 0,
          answersDeferred: answers.length,
          gradingStartedCount: 0,
          gradingFailure: null,
          error: "採点基準のファイルが選ばれていません。",
          failedFiles: [],
        };
      }
      const extras = materials.filter(
        (material) => material.path !== criteria.absolutePath,
      );
      const test = await createTest(deps.bridge, {
        name: group.name.trim(),
        criteriaPath: criteria.absolutePath,
        materials: extras,
      });
      testId = test.id;
      testStatus = test.status;
      materialCount = extras.length + 1;
    } else if (materials.length > 0 && testId !== null) {
      // `POST /tests/{id}/materials` は同一 (role, 内容) を再送しても既存を返すので、
      // 差分だけが増える（`docs/test-registration.md`）。profile・依存グラフ・配点には
      // 触れない。
      materialCount = await addMaterials(deps.bridge, testId, materials);
    }

    if (testId === null) {
      return {
        groupKey: group.key,
        name: group.name,
        testId: null,
        testStatus: null,
        createdTest,
        materialCount: 0,
        submissionCount: 0,
        duplicateCount: 0,
        answersDeferred: answers.length,
        gradingStartedCount: 0,
        gradingFailure: null,
        error: "取込先のテストが選ばれていません。",
        failedFiles: [],
      };
    }

    // 第 1 段: テストが `ready` でないなら答案は上げない (Issue #306 案 A)。
    // 登録が済んでから同じフォルダをもう一度取り込むと第 2 段で入る。
    if (!targetTestAcceptsAnswers(testStatus)) {
      return {
        groupKey: group.key,
        name: group.name,
        testId,
        testStatus,
        createdTest,
        materialCount,
        submissionCount: 0,
        duplicateCount: 0,
        answersDeferred: answers.length,
        gradingStartedCount: 0,
        gradingFailure: null,
        error: null,
        failedFiles: [],
      };
    }

    const answersResult = await importAnswers(deps, testId, answers);
    return {
      groupKey: group.key,
      name: group.name,
      testId,
      testStatus,
      createdTest,
      materialCount,
      submissionCount: answersResult.imported,
      duplicateCount: answersResult.duplicates,
      answersDeferred: 0,
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
      testStatus,
      createdTest,
      materialCount,
      submissionCount: 0,
      duplicateCount: 0,
      answersDeferred: 0,
      gradingStartedCount: 0,
      gradingFailure: null,
      error:
        error instanceof IntakeDataError ? error.message : "取込に失敗しました",
      failedFiles: [],
    };
  }
}

export async function importReview(
  deps: ImportDeps,
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

/** 取込画面の段。セッション保持にも使うので `features` ではなくここに置く。 */
export type IntakeStep = "choose" | "review" | "done";

/**
 * 取込画面のセッション（Issue #384）。
 *
 * 画面を離れると `IntakePage` が unmount し、フォルダ・ファイル・役割・取込先の
 * 選択が全部消えていた。**同じ選択を選び直させるのが「答案を後でまた再選択」の
 * 正体**なので、離れたときの状態をメモリに預けて復元する。
 *
 * **ディスクには書かない。** 再起動をまたいで古い選択が生き残ると、フォルダの
 * 中身が変わっていたときに画面と実ファイルがずれる。この Issue が解くのは
 * 「画面遷移で消える」ことだけ（司令官裁定 2026-09-12）。
 */
export interface IntakeSession {
  readonly step: IntakeStep;
  readonly templateId: string | null;
  readonly chosenFolderName: string | null;
  /** 復元時に実ファイルと突き合わせるための絶対パス。画面には出さない。 */
  readonly chosenFolderPath: string | null;
  readonly review: IntakeReviewState | null;
  readonly narrowedTestIds: readonly string[];
  readonly outcomes: readonly ImportOutcome[];
}

let intakeSession: IntakeSession | null = null;

export function loadIntakeSession(): IntakeSession | null {
  return intakeSession;
}

export function saveIntakeSession(session: IntakeSession): void {
  intakeSession = session;
}

/** 保持を捨てる。やり直し・取込成功・別フォルダ選択で呼ぶ。 */
export function resetIntakeSession(): void {
  intakeSession = null;
}

/**
 * 復元してよいかを、選んだフォルダを読み直して確かめる（司令官裁定 #5）。
 *
 * 画面に出す選択が現物とずれたまま取込ませないため、**各行が同じ
 * `sha256` とサイズでまだ存在するときだけ**復元する。新しく増えたファイルは
 * 選択に関係しないので無視し、消えた・変わったファイルが 1 つでもあれば
 * 復元しない（false）。
 */
export function sessionMatchesScan(
  review: IntakeReviewState,
  entries: readonly ScannedEntry[],
): boolean {
  const byPath = new Map(entries.map((entry) => [entry.relativePath, entry]));
  return review.groups
    .flatMap((group) => group.files)
    .every((file) => {
      const entry = byPath.get(file.relativePath);
      return (
        entry !== undefined &&
        entry.sha256 === file.sha256 &&
        entry.sizeBytes === file.sizeBytes
      );
    });
}

export { importedAnything, materialRoleWireValue, PDF_CONTENT_TYPE };
