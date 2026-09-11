import { describe, expect, it, vi } from "vitest";

import type { SidecarClient } from "../src/renderer/api/client.js";
import { ActionRequirements } from "../src/renderer/core/action-requirements.js";
import {
  SubmissionIntakeError,
  createSubmission,
  importReview,
  type IntakeBridge,
  type ImportDeps,
} from "../src/renderer/core/intake-data.js";
import {
  IntakeTargetKind,
  buildReviewState,
  targetTestAcceptsAnswers,
  type IntakeFileState,
  type IntakeGroupState,
  type IntakeReviewState,
} from "../src/renderer/core/intake-review.js";

const DIGEST = "0".repeat(64);

function file(
  relativePath: string,
  role: IntakeFileState["ruleRole"],
): IntakeFileState {
  return {
    relativePath,
    absolutePath: `/tmp/${relativePath}`,
    sha256: DIGEST,
    sizeBytes: 1,
    ruleRole: role,
    needsClassification: false,
    cachedClassification: false,
    classificationAttempted: false,
    proposedRole: null,
    proposalConfirmed: false,
    humanRole: null,
    excluded: false,
    answerTestId: null,
    proposedAnswerTestId: null,
    attributionAttempted: false,
  };
}

function group(patch: Partial<IntakeGroupState> = {}): IntakeGroupState {
  return {
    key: "subject-a",
    name: "subject-a",
    requiredRoles: ["grading_criteria"],
    targetKind: IntakeTargetKind.create,
    targetTestId: null,
    targetTestStatus: null,
    files: [
      file("subject-a/01_answers.pdf", "student_answer"),
      file("subject-a/02_criteria.pdf", "grading_criteria"),
    ],
    ...patch,
  };
}

function review(groups: IntakeGroupState[]): IntakeReviewState {
  return { groups, unitCost: null };
}

const SUBMISSION = {
  id: "sub-1",
  test_id: "test-1",
  state: "ai_processed",
  page_count: 1,
  student_label: null,
  created_at: new Date(Date.UTC(2026)).toISOString(),
  is_retry: false,
  original_filename: null,
  review_reason: null,
};

function mockClient(): SidecarClient {
  return {
    POST: vi.fn(async () => ({
      data: [],
      response: new Response(),
      error: undefined,
    })),
  } as unknown as SidecarClient;
}

function bridge(input: {
  submissionStatus?: number;
  submissionBody?: unknown;
  onCreateTest?: () => void;
  onCreateSubmission?: () => void;
  onAddMaterials?: () => void;
}): IntakeBridge {
  return {
    chooseFolder: vi.fn(async () => null),
    scanFolder: vi.fn(async () => ({ name: "batch", entries: [] })),
    sidecarMultipartUpload: vi.fn(async (request) => {
      if (request.urlPath === "/tests") {
        input.onCreateTest?.();
        return {
          status: 201,
          body: {
            id: "new-test",
            name: "subject-a",
            status: "draft",
            created_at: new Date(Date.UTC(2026)).toISOString(),
            subject: null,
          },
        };
      }
      if (request.urlPath.endsWith("/materials")) {
        input.onAddMaterials?.();
        return { status: 200, body: [] };
      }
      if (request.urlPath.endsWith("/submissions")) {
        input.onCreateSubmission?.();
        return {
          status: input.submissionStatus ?? 201,
          body: input.submissionBody ?? SUBMISSION,
        };
      }
      return { status: 200, body: [] };
    }),
  };
}

function deps(
  overrides: Partial<ImportDeps> = {},
): ImportDeps & { bridge: IntakeBridge; client: SidecarClient } {
  return {
    bridge: bridge({}),
    client: mockClient(),
    ...overrides,
  };
}

describe("intake two-stage import (Issue #306 案 A)", () => {
  it("第 1 段: 新しいテストは作るが、答案はまだ上げない", async () => {
    let submissions = 0;
    const result = await importReview(
      deps({
        bridge: bridge({ onCreateSubmission: () => (submissions += 1) }),
      }),
      review([group()]),
    );

    expect(submissions).toBe(0);
    expect(result[0]?.answersDeferred).toBe(1);
    expect(result[0]?.testStatus).toBe("draft");
    expect(result[0]?.submissionCount).toBe(0);
  });

  it("第 2 段: ready な既存テストには答案を上げ、採点を起動する", async () => {
    let submissions = 0;
    let grading = 0;
    const client = {
      POST: vi.fn(async () => {
        grading += 1;
        return { data: [], response: new Response(), error: undefined };
      }),
    } as unknown as SidecarClient;

    const result = await importReview(
      {
        bridge: bridge({ onCreateSubmission: () => (submissions += 1) }),
        client,
      },
      review([
        group({
          targetKind: IntakeTargetKind.existing,
          targetTestId: "test-1",
          targetTestStatus: "ready",
        }),
      ]),
    );

    expect(submissions).toBe(1);
    expect(grading).toBe(1);
    expect(result[0]?.answersDeferred).toBe(0);
  });

  it("登録途中の既存テストには資料だけ足し、答案は保留する", async () => {
    let submissions = 0;
    let materials = 0;
    const result = await importReview(
      deps({
        bridge: bridge({
          onCreateSubmission: () => (submissions += 1),
          onAddMaterials: () => (materials += 1),
        }),
      }),
      review([
        group({
          targetKind: IntakeTargetKind.existing,
          targetTestId: "test-1",
          targetTestStatus: "draft",
        }),
      ]),
    );

    expect(materials).toBe(1);
    expect(submissions).toBe(0);
    expect(result[0]?.answersDeferred).toBe(1);
  });

  it("targetTestAcceptsAnswers は ready だけを通す", () => {
    expect(targetTestAcceptsAnswers("ready")).toBe(true);
    expect(targetTestAcceptsAnswers("draft")).toBe(false);
    expect(targetTestAcceptsAnswers(null)).toBe(false);
  });
});

describe("intake reuses the existing test (Issue #306)", () => {
  it("同じ名前の既存テストがあれば作成せず再利用する", () => {
    const state = buildReviewState({
      plan: {
        groups: [
          {
            key: "subject-a",
            suggested_name: "subject-a",
            missing_required_roles_if_new: [],
            files: [
              {
                relative_path: "subject-a/01_answers.pdf",
                sha256: DIGEST,
                size_bytes: 1,
                role: "student_answer",
                role_source: "rule",
                classification: "not_needed",
              },
            ],
          },
        ],
        estimate: { pending: 0, cached: 0, unsupported: 0, not_needed: 1 },
      },
      folder: {
        name: "batch",
        entries: [
          {
            relativePath: "subject-a/01_answers.pdf",
            absolutePath: "/tmp/subject-a/01_answers.pdf",
            sizeBytes: 1,
            sha256: DIGEST,
          },
        ],
      },
      requiredRoles: ["grading_criteria"],
      unitCost: null,
      existingTests: [
        {
          id: "test-1",
          name: "subject-a",
          status: "ready",
          created_at: new Date(Date.UTC(2026)).toISOString(),
        },
      ],
    });

    const reused = state.groups[0];
    expect(reused?.targetKind).toBe(IntakeTargetKind.existing);
    expect(reused?.targetTestId).toBe("test-1");
    expect(reused?.targetTestStatus).toBe("ready");
  });
});

describe("createSubmission keeps status and detail (Issue #306)", () => {
  async function errorFor(
    status: number,
    body: unknown,
  ): Promise<SubmissionIntakeError> {
    try {
      await createSubmission(
        bridge({ submissionStatus: status, submissionBody: body }),
        "test-1",
        "/tmp/subject-a/01_answers.pdf",
      );
    } catch (error) {
      if (error instanceof SubmissionIntakeError) {
        return error;
      }
      throw error;
    }
    throw new Error("createSubmission should have thrown");
  }

  it("409 の文字列 detail は not-ready とその detail を保持する", async () => {
    const error = await errorFor(409, {
      detail: "test 'test-1' is not ready to accept submissions yet",
    });
    expect(error.kind).toBe("not-ready");
    expect(error.status).toBe(409);
    expect(error.detail).toContain("not ready");
  });

  it("409 の submission_id 付き detail は再取込の競合", async () => {
    const error = await errorFor(409, {
      detail: { message: "already being retried", submission_id: "sub-9" },
    });
    expect(error.kind).toBe("retry-conflict");
    expect(error.detail).toBe("already being retried");
  });

  it("400 は rejected、500 は server に分ける", async () => {
    expect((await errorFor(400, { detail: "bad pdf" })).kind).toBe("rejected");
    expect((await errorFor(500, { detail: "boom" })).kind).toBe("server");
  });
});

describe("intake failure reasons are not discarded (Issue #306)", () => {
  async function failureMessage(
    status: number,
    body: unknown,
  ): Promise<string | null> {
    const result = await importReview(
      deps({
        bridge: bridge({ submissionStatus: status, submissionBody: body }),
      }),
      review([
        group({
          targetKind: IntakeTargetKind.existing,
          targetTestId: "test-1",
          targetTestStatus: "ready",
        }),
      ]),
    );
    return result[0]?.error ?? null;
  }

  it("登録未完了の 409 と 5xx で違う文言を出す", async () => {
    const notReady = await failureMessage(409, {
      detail: "test 'test-1' is not ready to accept submissions yet",
    });
    const server = await failureMessage(500, { detail: "boom" });

    expect(notReady).toBe(ActionRequirements.submissionTestNotReady.message);
    expect(server).toBe(ActionRequirements.submissionServerError.message);
    expect(notReady).not.toBe(server);
  });

  it("既存の重複 409 は失敗ではなく重複として数える", async () => {
    const result = await importReview(
      deps({
        bridge: bridge({
          submissionStatus: 409,
          submissionBody: {
            detail: { message: "duplicate", existing_submission_id: "sub-9" },
          },
        }),
      }),
      review([
        group({
          targetKind: IntakeTargetKind.existing,
          targetTestId: "test-1",
          targetTestStatus: "ready",
        }),
      ]),
    );

    expect(result[0]?.error).toBeNull();
    expect(result[0]?.duplicateCount).toBe(1);
    expect(result[0]?.submissionCount).toBe(0);
  });
});
