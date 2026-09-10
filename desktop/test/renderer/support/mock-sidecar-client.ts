import { vi } from "vitest";

import type { SidecarClient } from "../../../src/renderer/api/client.js";
import type {
  SubmissionResponse,
  TestResponse,
} from "../../../src/renderer/core/home-dashboard.js";

export interface MockSidecarHandlers {
  listTestRegistrations?: () => Promise<TestResponse[]>;
  listSubmissions?: (testId: string) => Promise<SubmissionResponse[]>;
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
  testId: string;
  state: string;
  createdDay?: number;
  studentLabel?: string | null;
}): SubmissionResponse {
  const day = input.createdDay ?? 1;
  return {
    id: input.id,
    test_id: input.testId,
    state: input.state,
    page_count: 1,
    student_label: input.studentLabel ?? null,
    created_at: new Date(Date.UTC(2026, 1, day)).toISOString(),
    is_retry: false,
    original_filename: null,
    review_reason: null,
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
      if (path === "/tests/{test_id}/submissions") {
        const testId = init?.params?.path?.test_id;
        if (testId === undefined) {
          return {
            data: undefined,
            response: new Response(null, { status: 400 }),
            error: { message: "missing test id" },
          };
        }
        const data = handlers.listSubmissions
          ? await handlers.listSubmissions(testId)
          : [];
        return { data, response: new Response(), error: undefined };
      }
      return {
        data: undefined,
        response: new Response(null, { status: 404 }),
        error: { message: "not found" },
      };
    }),
    POST: vi.fn(),
    PUT: vi.fn(),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
    use: vi.fn(),
    eject: vi.fn(),
  } as unknown as SidecarClient;
}
