import { vi } from "vitest";

import type { SidecarClient } from "../../../src/renderer/api/client.js";
import type { components } from "../../../src/renderer/api/generated/schema.js";
import type { IntakeBridge } from "../../../src/renderer/core/intake-data.js";
import type { ScannedEntry } from "../../../src/shared/folder-scan.js";
import {
  createMockSidecarClient,
  type MockSidecarHandlers,
} from "./mock-sidecar-client.js";

const DIGEST =
  "0000000000000000000000000000000000000000000000000000000000000000";

export type IntakeTemplateModel = components["schemas"]["IntakeTemplateModel"];
export type IntakePlanResponse = components["schemas"]["IntakePlanResponse"];
export type PlannedFileModel = components["schemas"]["PlannedFileModel"];

export function defaultTemplate(): IntakeTemplateModel {
  return {
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
      {
        scope: "file",
        pattern: "02_*",
        role: "grading_criteria",
        requirement: "required",
      },
    ],
  };
}

export function plannedFile(
  relativePath: string,
  input: {
    role?: components["schemas"]["MaterialRole"] | null;
    classification?: components["schemas"]["ClassificationNeed"];
  } = {},
): PlannedFileModel {
  return {
    relative_path: relativePath,
    sha256: DIGEST,
    size_bytes: 1,
    role: input.role ?? null,
    role_source:
      input.role === null || input.role === undefined ? "unresolved" : "rule",
    classification: input.classification ?? "not_needed",
  };
}

export function buildPlan(
  files: PlannedFileModel[],
  pending = 0,
): IntakePlanResponse {
  return {
    groups: [
      {
        key: "subject-a",
        suggested_name: "subject-a",
        missing_required_roles_if_new: [],
        files,
      },
    ],
    estimate: {
      pending,
      cached: 0,
      unsupported: 0,
      not_needed: files.length - pending,
    },
  };
}

export function scannedFolder(paths: readonly string[]): {
  name: string;
  entries: ScannedEntry[];
} {
  return {
    name: "batch",
    entries: paths.map((relativePath) => ({
      relativePath,
      absolutePath: `/tmp/${relativePath}`,
      sizeBytes: 1,
      sha256: DIGEST,
    })),
  };
}

export interface IntakeMockHandlers extends MockSidecarHandlers {
  listIntakeTemplates?: () => Promise<IntakeTemplateModel[]>;
  intakeCost?: () => Promise<number | null>;
  classificationAvailability?: () => Promise<
    components["schemas"]["ClassificationAvailabilityResponse"]
  >;
  planIntake?: () => Promise<IntakePlanResponse>;
  startGrading?: (submissionId: string) => Promise<unknown>;
}

export function createIntakeMockClient(
  handlers: IntakeMockHandlers = {},
): SidecarClient {
  const base = createMockSidecarClient(handlers);
  return {
    ...base,
    GET: vi.fn(async (path, init) => {
      if (path === "/intake-templates") {
        return {
          data: handlers.listIntakeTemplates
            ? await handlers.listIntakeTemplates()
            : [defaultTemplate()],
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/intake-cost") {
        return {
          data: {
            classification_unit_cost: handlers.intakeCost
              ? await handlers.intakeCost()
              : null,
          },
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/intake/classification-availability") {
        return {
          data: handlers.classificationAvailability
            ? await handlers.classificationAvailability()
            : { available: true, reason: null },
          response: new Response(),
          error: undefined,
        };
      }
      const fallback = base.GET as (
        requestPath: string,
        requestInit?: unknown,
      ) => Promise<unknown>;
      return (await fallback(path, init)) as Awaited<
        ReturnType<SidecarClient["GET"]>
      >;
    }),
    POST: vi.fn(async (path, init) => {
      if (path === "/intake/plan") {
        return {
          data: handlers.planIntake
            ? await handlers.planIntake()
            : buildPlan([]),
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/submissions/{submission_id}/jobs") {
        const submissionId = init?.params?.path?.submission_id;
        if (submissionId !== undefined && handlers.startGrading) {
          await handlers.startGrading(submissionId);
        }
        return { data: [], response: new Response(), error: undefined };
      }
      return {
        data: undefined,
        response: new Response(null, { status: 404 }),
        error: { message: "not found" },
      };
    }),
  } as unknown as SidecarClient;
}

export function createIntakeBridge(
  input: {
    folderPaths?: readonly string[];
    classifyMaterial?: (path: string) => Promise<unknown>;
    createSubmission?: () => Promise<unknown>;
    createTest?: () => Promise<unknown>;
  } = {},
): IntakeBridge {
  const folder = scannedFolder(input.folderPaths ?? []);
  return {
    chooseFolder: vi.fn(async () => "/tmp/batch"),
    scanFolder: vi.fn(async () => folder),
    sidecarMultipartUpload: vi.fn(async (request) => {
      if (request.urlPath === "/intake/classify") {
        if (input.classifyMaterial) {
          await input.classifyMaterial(request.fileFields[0]?.filePath ?? "");
        }
        return {
          status: 200,
          body: { role: "reference", confidence: 0.9, cached: false },
        };
      }
      if (request.urlPath === "/tests") {
        if (input.createTest) {
          await input.createTest();
        }
        return {
          status: 201,
          body: {
            id: "test-1",
            name: "subject-a",
            status: "draft",
            created_at: new Date(Date.UTC(2026)).toISOString(),
            subject: null,
          },
        };
      }
      if (request.urlPath.endsWith("/submissions")) {
        if (input.createSubmission) {
          await input.createSubmission();
        }
        return {
          status: 201,
          body: {
            id: "sub-1",
            test_id: "test-1",
            state: "ai_processed",
            page_count: 1,
            student_label: null,
            created_at: new Date(Date.UTC(2026)).toISOString(),
            is_retry: false,
            original_filename: null,
            review_reason: null,
          },
        };
      }
      return { status: 200, body: [] };
    }),
  };
}
