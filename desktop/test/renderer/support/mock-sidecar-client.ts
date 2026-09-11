import { vi } from "vitest";

import type { SidecarClient } from "../../../src/renderer/api/client.js";
import type {
  BulkExportResponse,
  ExportRequestResponse,
  ExportResponse,
  JobResponse,
} from "../../../src/renderer/core/export-data.js";
import type {
  SubmissionResponse,
  SubmissionReviewProgressResponse,
  TestResponse,
} from "../../../src/renderer/core/submission-queue-data.js";
import type {
  ApiKeySettingsResponse,
  ApiKeyStatusModel,
  IntakeCostModel,
  IntakeTemplateModel,
  VerifyApiKeyResponse,
} from "../../../src/renderer/api/settings-data.js";

export interface MockSidecarHandlers {
  listTestRegistrations?: () => Promise<TestResponse[]>;
  getTest?: (testId: string) => Promise<TestResponse>;
  listSubmissions?: (testId: string) => Promise<SubmissionResponse[]>;
  listReviewProgress?: (
    testId: string,
  ) => Promise<SubmissionReviewProgressResponse[]>;
  requestExport?: (
    submissionId: string,
  ) => Promise<ExportRequestResponse | { status: number; body: unknown }>;
  getJob?: (jobId: string) => Promise<JobResponse>;
  listExports?: (submissionId: string) => Promise<ExportResponse[]>;
  retryJob?: (jobId: string) => Promise<JobResponse>;
  cancelJob?: (jobId: string) => Promise<JobResponse>;
  requestBulkExport?: (
    testId: string,
    submissionIds: readonly string[],
  ) => Promise<BulkExportResponse>;
  getExportFile?: (exportId: string) => Promise<Uint8Array>;
  getApiKeySettings?: () => Promise<ApiKeySettingsResponse>;
  saveApiKey?: (
    slotId: string,
    value: string,
  ) => Promise<ApiKeySettingsResponse>;
  deleteApiKey?: (slotId: string) => Promise<ApiKeySettingsResponse>;
  verifyApiKey?: (slotId: string) => Promise<VerifyApiKeyResponse>;
  listIntakeTemplates?: () => Promise<IntakeTemplateModel[]>;
  saveIntakeTemplates?: (
    templates: IntakeTemplateModel[],
  ) => Promise<IntakeTemplateModel[]>;
  getIntakeCost?: () => Promise<IntakeCostModel>;
  saveIntakeCost?: (cost: number | null) => Promise<IntakeCostModel>;
}

export function buildTest(input: {
  id: string;
  name?: string;
  status?: string;
  createdDay?: number;
}): TestResponse {
  const day = input.createdDay ?? 1;
  return {
    id: input.id,
    name: input.name ?? "国語 第1回",
    status: input.status ?? "ready",
    created_at: new Date(Date.UTC(2026, 0, day)).toISOString(),
    subject: null,
  };
}

export function buildSubmission(input: {
  id: string;
  testId?: string;
  state: string;
  createdDay?: number;
  studentLabel?: string | null;
  reviewReason?: string | null;
  originalFilename?: string | null;
}): SubmissionResponse {
  const day = input.createdDay ?? 1;
  return {
    id: input.id,
    test_id: input.testId ?? "t1",
    state: input.state,
    page_count: 1,
    student_label: input.studentLabel ?? null,
    created_at: new Date(Date.UTC(2026, 1, day)).toISOString(),
    is_retry: false,
    original_filename: input.originalFilename ?? null,
    review_reason: input.reviewReason ?? null,
  };
}

export function buildProgress(input: {
  id: string;
  total?: number;
  confirmed?: number;
  manualGrading?: number;
}): SubmissionReviewProgressResponse {
  return {
    submission_id: input.id,
    total_questions: input.total ?? 5,
    confirmed_questions: input.confirmed ?? 0,
    manual_grading_questions: input.manualGrading ?? 0,
  };
}

export function buildApiKeyStatus(
  input: Partial<ApiKeyStatusModel> & { id?: string } = {},
): ApiKeyStatusModel {
  return {
    id: input.id ?? "openrouter",
    label: input.label ?? "OpenRouter",
    configured: input.configured ?? false,
    key_source: input.key_source ?? "none",
    key_variable: input.key_variable ?? "AUTO_SCORING_OPENROUTER_API_KEY",
    model: input.model ?? "google/gemini-2.5-flash",
    model_source: input.model_source ?? "builtin_default",
    console_url: input.console_url ?? "https://openrouter.ai/settings/keys",
  };
}

export function buildApiKeySettings(
  input: Partial<ApiKeySettingsResponse> = {},
): ApiKeySettingsResponse {
  return {
    keys: input.keys ?? [buildApiKeyStatus()],
    restart_required: input.restart_required ?? false,
    store_unavailable_reason: input.store_unavailable_reason ?? null,
    transport_order: input.transport_order ?? "openrouter",
    transport_source: input.transport_source ?? "builtin_default",
  };
}

export function buildVerifyApiKeyResponse(
  input: Partial<VerifyApiKeyResponse> = {},
): VerifyApiKeyResponse {
  return {
    result: input.result ?? "ok",
    detail: input.detail ?? "疎通しました。",
    key_source: input.key_source ?? "credential_store",
    status_code: input.status_code ?? 200,
  };
}

export function createMockSidecarClient(
  handlers: MockSidecarHandlers = {},
): SidecarClient {
  return {
    GET: vi.fn(async (path, init) => {
      if (path === "/test-registrations") {
        const data = handlers.listTestRegistrations
          ? await handlers.listTestRegistrations()
          : [];
        return { data, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}") {
        const testId = init?.params?.path?.test_id;
        if (testId === undefined) {
          return {
            data: undefined,
            response: new Response(null, { status: 400 }),
            error: { message: "missing test id" },
          };
        }
        try {
          if (handlers.getTest) {
            const data = await handlers.getTest(testId);
            return { data, response: new Response(), error: undefined };
          }
          if (handlers.listTestRegistrations) {
            const all = await handlers.listTestRegistrations();
            const found = all.find((t) => t.id === testId);
            if (found) {
              return {
                data: found,
                response: new Response(),
                error: undefined,
              };
            }
          }
          return {
            data: buildTest({ id: testId }),
            response: new Response(),
            error: undefined,
          };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/tests/{test_id}/submissions") {
        const testId = init?.params?.path?.test_id;
        if (testId === undefined) {
          return {
            data: undefined,
            response: new Response(null, { status: 400 }),
            error: { message: "missing test id" },
          };
        }
        try {
          const data = handlers.listSubmissions
            ? await handlers.listSubmissions(testId)
            : [];
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/tests/{test_id}/review-progress") {
        const testId = init?.params?.path?.test_id;
        if (testId === undefined) {
          return {
            data: undefined,
            response: new Response(null, { status: 400 }),
            error: { message: "missing test id" },
          };
        }
        try {
          const data = handlers.listReviewProgress
            ? await handlers.listReviewProgress(testId)
            : [];
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/submissions/{submission_id}/exports") {
        const submissionId = init?.params?.path?.submission_id;
        if (submissionId === undefined) {
          return {
            data: undefined,
            response: new Response(null, { status: 400 }),
            error: { message: "missing submission id" },
          };
        }
        try {
          const data = handlers.listExports
            ? await handlers.listExports(submissionId)
            : [];
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/exports/{export_id}/file") {
        const exportId = init?.params?.path?.export_id;
        if (exportId === undefined) {
          return {
            data: undefined,
            response: new Response(null, { status: 400 }),
            error: { message: "missing export id" },
          };
        }
        try {
          const bytes = handlers.getExportFile
            ? await handlers.getExportFile(exportId)
            : new Uint8Array([1]);
          const blob = new Blob([Uint8Array.from(bytes)], {
            type: "application/pdf",
          });
          return { data: blob, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/jobs/{job_id}") {
        const jobId = init?.params?.path?.job_id;
        if (jobId === undefined) {
          return {
            data: undefined,
            response: new Response(null, { status: 400 }),
            error: { message: "missing job id" },
          };
        }
        try {
          if (handlers.getJob) {
            const data = await handlers.getJob(jobId);
            return { data, response: new Response(), error: undefined };
          }
          return {
            data: {
              id: jobId,
              kind: "export_submission",
              state: "succeeded",
              attempts: 1,
              max_attempts: 1,
              submission_id: "s1",
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            } as unknown as JobResponse,
            response: new Response(),
            error: undefined,
          };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/submissions/{submission_id}") {
        const submissionId = init?.params?.path?.submission_id ?? "sub-1";
        return {
          data: {
            id: submissionId,
            test_id: "t1",
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
        return {
          data: [
            {
              id: "q-1",
              test_id: init?.params?.path?.test_id ?? "t1",
              number: "1",
              page: 1,
              points: 5,
              scoring_method: "additive",
              rubric: [],
            },
          ],
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/tests/{test_id}/dependency-graph") {
        return {
          data: {
            id: "graph-1",
            test_id: init?.params?.path?.test_id ?? "t1",
            status: "confirmed",
            version: 1,
            question_ids: ["q-1"],
            edges: [],
            layers: [["q-1"]],
            unresolved: [],
            confirmed_at: "2026-01-01T00:00:00Z",
          },
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/submissions/{submission_id}/jobs") {
        return {
          data: [
            {
              id: "job-1",
              kind: "grading",
              submission_id: init?.params?.path?.submission_id ?? "sub-1",
              question_id: "q-1",
              state: "succeeded",
              usable: true,
              attempts: 1,
              max_attempts: 3,
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
          ],
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/submissions/{submission_id}/pages") {
        return {
          data: {
            page_count: 1,
            pages: [
              {
                page_index: 0,
                displayed_width: 595,
                displayed_height: 842,
                rotation: 0,
              },
            ],
          },
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/submissions/{submission_id}/pages/{page_index}/image") {
        const blob = new Blob([new Uint8Array([137, 80, 78, 71])], {
          type: "image/png",
        });
        return { data: blob, response: new Response(), error: undefined };
      }
      if (
        path ===
          "/submissions/{submission_id}/questions/{question_id}/recognitions" ||
        path ===
          "/submissions/{submission_id}/questions/{question_id}/grades" ||
        path ===
          "/submissions/{submission_id}/questions/{question_id}/annotations" ||
        path === "/submissions/{submission_id}/questions/{question_id}/reviews"
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
      if (path === "/settings/api-keys") {
        try {
          const data = handlers.getApiKeySettings
            ? await handlers.getApiKeySettings()
            : buildApiKeySettings();
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/intake-templates") {
        try {
          const data = handlers.listIntakeTemplates
            ? await handlers.listIntakeTemplates()
            : [
                {
                  id: "serial-number-prefix",
                  name: "連番の接頭辞 (既定)",
                  split_child_directories: true,
                  rules: [
                    {
                      scope: "file",
                      pattern: "01_*",
                      role: "student_answer",
                      requirement: "required",
                    },
                  ],
                },
              ];
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/intake-cost") {
        try {
          const data = handlers.getIntakeCost
            ? await handlers.getIntakeCost()
            : { classification_unit_cost: null };
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      return {
        data: undefined,
        response: new Response(null, { status: 404 }),
        error: { message: "not found" },
      };
    }),
    POST: vi.fn(async (path, init) => {
      if (path === "/submissions/{submission_id}/export") {
        const submissionId = init?.params?.path?.submission_id;
        if (submissionId === undefined) {
          return {
            data: undefined,
            response: new Response(null, { status: 400 }),
            error: { message: "missing submission id" },
          };
        }
        try {
          if (handlers.requestExport) {
            const data = await handlers.requestExport(submissionId);
            if (
              typeof data === "object" &&
              data !== null &&
              "status" in data &&
              "body" in data
            ) {
              const conflict = data as { status: number; body: unknown };
              return {
                data: undefined,
                response: new Response(null, { status: conflict.status }),
                error: conflict.body,
              };
            }
            return {
              data: data as ExportRequestResponse,
              response: new Response(),
              error: undefined,
            };
          }
          return {
            data: {
              decision: "reuse_existing",
              export: {
                id: `exp-${submissionId}`,
                job_id: `job-${submissionId}`,
                submission_id: submissionId,
                file_path: `exports/submission_${submissionId}.pdf`,
                file_sha256: "0".repeat(64),
                created_at: new Date().toISOString(),
              },
            } as ExportRequestResponse,
            response: new Response(),
            error: undefined,
          };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/jobs/{job_id}/retry") {
        const jobId = init?.params?.path?.job_id;
        if (jobId === undefined) {
          return {
            data: undefined,
            response: new Response(null, { status: 400 }),
            error: { message: "missing job id" },
          };
        }
        try {
          const data = handlers.retryJob
            ? await handlers.retryJob(jobId)
            : ({
                id: jobId,
                kind: "export",
                state: "queued",
                attempts: 0,
                max_attempts: 3,
                submission_id: "s1",
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              } as JobResponse);
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/settings/api-keys/{slot_id}/verify") {
        const slotId = init?.params?.path?.slot_id;
        try {
          const data = handlers.verifyApiKey
            ? await handlers.verifyApiKey(slotId ?? "")
            : buildVerifyApiKeyResponse();
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/jobs/{job_id}/cancel") {
        const jobId = init?.params?.path?.job_id;
        if (jobId === undefined) {
          return {
            data: undefined,
            response: new Response(null, { status: 400 }),
            error: { message: "missing job id" },
          };
        }
        try {
          const data = handlers.cancelJob
            ? await handlers.cancelJob(jobId)
            : ({
                id: jobId,
                kind: "export",
                state: "cancelled",
                attempts: 0,
                max_attempts: 3,
                submission_id: "s1",
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              } as JobResponse);
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/tests/{test_id}/export") {
        const testId = init?.params?.path?.test_id;
        if (testId === undefined) {
          return {
            data: undefined,
            response: new Response(null, { status: 400 }),
            error: { message: "missing test id" },
          };
        }
        try {
          const body = init?.body as { submission_ids?: string[] } | undefined;
          const submissionIds = body?.submission_ids ?? [];
          const data = handlers.requestBulkExport
            ? await handlers.requestBulkExport(testId, submissionIds)
            : ({
                test_id: testId,
                items: submissionIds.map((submissionId) => ({
                  submission_id: submissionId,
                  status: "reused",
                  export: {
                    id: `exp-${submissionId}`,
                    job_id: `job-${submissionId}`,
                    submission_id: submissionId,
                    file_path: `exports/${submissionId}_corrected.pdf`,
                    file_sha256: "0".repeat(64),
                    created_at: new Date().toISOString(),
                  },
                })),
              } as BulkExportResponse);
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      return {
        data: undefined,
        response: new Response(null, { status: 404 }),
        error: { message: "not found" },
      };
    }),
    PUT: vi.fn(async (path, init) => {
      if (path === "/settings/api-keys/{slot_id}") {
        const slotId = init?.params?.path?.slot_id;
        const value =
          (init?.body as { value?: string } | undefined)?.value ?? "";
        try {
          const data = handlers.saveApiKey
            ? await handlers.saveApiKey(slotId ?? "", value)
            : buildApiKeySettings({
                keys: [
                  buildApiKeyStatus({
                    id: slotId,
                    configured: true,
                    key_source: "credential_store",
                  }),
                ],
                restart_required: true,
              });
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/intake-templates") {
        const templates =
          (init?.body as { templates?: IntakeTemplateModel[] } | undefined)
            ?.templates ?? [];
        try {
          const data = handlers.saveIntakeTemplates
            ? await handlers.saveIntakeTemplates(templates)
            : templates;
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      if (path === "/intake-cost") {
        const cost =
          (
            init?.body as
              { classification_unit_cost?: number | null } | undefined
          )?.classification_unit_cost ?? null;
        try {
          const data = handlers.saveIntakeCost
            ? await handlers.saveIntakeCost(cost)
            : { classification_unit_cost: cost };
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      return {
        data: undefined,
        response: new Response(null, { status: 404 }),
        error: { message: "not found" },
      };
    }),
    PATCH: vi.fn(),
    DELETE: vi.fn(async (path, init) => {
      if (path === "/settings/api-keys/{slot_id}") {
        const slotId = init?.params?.path?.slot_id;
        try {
          const data = handlers.deleteApiKey
            ? await handlers.deleteApiKey(slotId ?? "")
            : buildApiKeySettings({
                keys: [
                  buildApiKeyStatus({
                    id: slotId,
                    configured: false,
                    key_source: "none",
                  }),
                ],
              });
          return { data, response: new Response(), error: undefined };
        } catch (err) {
          return {
            data: undefined,
            response: new Response(null, { status: 500 }),
            error: {
              message: err instanceof Error ? err.message : String(err),
            },
          };
        }
      }
      return {
        data: undefined,
        response: new Response(null, { status: 404 }),
        error: { message: "not found" },
      };
    }),
    use: vi.fn(),
    eject: vi.fn(),
  } as unknown as SidecarClient;
}
