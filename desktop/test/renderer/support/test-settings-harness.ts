import { vi } from "vitest";

import type { SidecarClient } from "../../../src/renderer/api/client.js";
import type { components } from "../../../src/renderer/api/generated/schema.js";
import {
  buildTest,
  createMockSidecarClient,
  type MockSidecarHandlers,
} from "./mock-sidecar-client.js";

type ProfileResponse = components["schemas"]["ProfileResponse"];
type CriteriaResponse = components["schemas"]["CriteriaResponse"];
type DependencyGraphResponse = components["schemas"]["DependencyGraphResponse"];
type AnswerLayoutResponse = components["schemas"]["AnswerLayoutResponse"];

const PAGE = { width_pt: 595, height_pt: 842 };
const LAYOUT_PAGE: components["schemas"]["PageGeometryResponse"] = {
  page_index: 0,
  displayed_width: 595,
  displayed_height: 842,
  rotation: 0,
};
const TINY_PNG = Uint8Array.from(
  atob(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  ),
  (char) => char.charCodeAt(0),
);

type DetectAnswerAreasResult =
  | { kind: "profile"; profile: ProfileResponse }
  | {
      kind: "error";
      status: number;
      detail: string;
      /** Set to model the structured 429 body (Issue #304). */
      retryAfterSeconds?: number | null;
    };

export function createTestSettingsMockClient(
  input: {
    testId?: string;
    testStatus?: string;
    handlers?: MockSidecarHandlers;
    detectAnswerAreas?: () => DetectAnswerAreasResult;
    estimate?: {
      page_count: number;
      max_pages: number;
      estimated_cost: number | null;
      unit_cost: number | null;
    };
  } = {},
): { client: SidecarClient; applyLayoutUpload: () => AnswerLayoutResponse } {
  const testId = input.testId ?? "t-reg";
  let testStatus = input.testStatus ?? "draft";
  let profile: ProfileResponse | null = null;
  let criteria: CriteriaResponse | null = null;
  let graph: DependencyGraphResponse | null = null;
  let layout: AnswerLayoutResponse = {
    test_id: testId,
    page_count: null,
    detection_available: false,
    detection_unavailable_reason: "E2E stub",
    dropped_region_count: 0,
  };
  let profileRevision = 0;
  let criteriaRevision = 0;
  let graphVersion = 0;
  const questionNumbers: string[] = [];

  const buildProfile = (
    overrides: Partial<ProfileResponse> &
      Pick<ProfileResponse, "revision" | "status" | "regions">,
  ): ProfileResponse => ({
    test_id: testId,
    question_numbers: questionNumbers,
    unassigned_region_ids: [],
    undetected_question_numbers: [],
    absent_question_numbers: [],
    reading_order_conflicts: [],
    pages: [PAGE],
    ...overrides,
  });

  const applyLayoutUpload = (): AnswerLayoutResponse => {
    layout = {
      test_id: testId,
      page_count: 1,
      detection_available: true,
      detection_unavailable_reason: null,
      dropped_region_count: 0,
    };
    profileRevision += 1;
    profile = buildProfile({
      status: "draft",
      revision: profileRevision,
      regions: [],
    });
    return layout;
  };

  const base = createMockSidecarClient({
    ...input.handlers,
    getTest: async (id) =>
      buildTest({ id, status: testStatus, name: "E2E 理科" }),
  });

  const client = {
    GET: vi.fn(async (path, init) => {
      if (path === "/tests/{test_id}/profile") {
        if (profile === null) {
          return {
            data: undefined,
            response: new Response(null, { status: 404 }),
            error: { message: "not found" },
          };
        }
        return { data: profile, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/criteria") {
        if (criteria === null) {
          return {
            data: undefined,
            response: new Response(null, { status: 404 }),
            error: { message: "not found" },
          };
        }
        return { data: criteria, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/dependency-graph") {
        if (graph === null) {
          return {
            data: undefined,
            response: new Response(null, { status: 404 }),
            error: { message: "not found" },
          };
        }
        return { data: graph, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/answer-layout") {
        return { data: layout, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/answer-layout/pages") {
        return {
          data: {
            page_count: layout.page_count ?? 0,
            pages: layout.page_count ? [LAYOUT_PAGE] : [],
          },
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/tests/{test_id}/questions") {
        return {
          data: questionNumbers.map((number, index) => ({
            id: `${testId}:${number}`,
            test_id: testId,
            number,
            page: index + 1,
            points: 10,
            scoring_method: "additive",
            rubric: [],
          })),
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/tests/{test_id}/answer-layout/pages/{page_index}/image") {
        const blob = new Blob([TINY_PNG], {
          type: "image/png",
        });
        return { data: blob, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/criteria/estimate") {
        return {
          data: input.estimate ?? {
            page_count: 1,
            max_pages: 50,
            estimated_cost: null,
            unit_cost: null,
          },
          response: new Response(),
          error: undefined,
        };
      }
      return base.GET(path, init);
    }),
    POST: vi.fn(async (path, init) => {
      const id = init?.params?.path?.test_id ?? testId;
      if (path === "/tests/{test_id}/criteria/confirm") {
        if (criteria === null) {
          return {
            data: undefined,
            response: new Response(null, { status: 404 }),
            error: { message: "missing" },
          };
        }
        criteria = {
          ...criteria,
          status: "confirmed",
          revision: criteriaRevision,
        };
        questionNumbers.splice(
          0,
          questionNumbers.length,
          ...criteria.questions.map((q) => q.number),
        );
        return { data: criteria, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/profile/confirm") {
        if (profile === null) {
          return {
            data: undefined,
            response: new Response(null, { status: 404 }),
            error: { message: "missing" },
          };
        }
        profile = {
          ...profile,
          status: "confirmed",
          revision: profileRevision,
        };
        return { data: profile, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/dependency-graph/analyze") {
        graphVersion += 1;
        graph = {
          id: `graph-${graphVersion}`,
          test_id: id,
          status: "draft",
          version: graphVersion,
          question_ids: questionNumbers.map((number) => `${id}:${number}`),
          edges: [],
          layers: [questionNumbers.map((number) => `${id}:${number}`)],
          unresolved: [],
          confirmed_at: null,
          created_at: "2026-01-01T00:00:00Z",
        };
        return { data: graph, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/dependency-graph/confirm") {
        if (graph === null) {
          return {
            data: undefined,
            response: new Response(null, { status: 404 }),
            error: { message: "missing" },
          };
        }
        graph = {
          ...graph,
          status: "confirmed",
          confirmed_at: "2026-01-01T00:00:00Z",
        };
        return { data: graph, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/complete-registration") {
        testStatus = "ready";
        return {
          data: {
            test: buildTest({ id, status: "ready", name: "E2E 理科" }),
            profile_confirmed: true,
            dependency_graph_confirmed: true,
          },
          response: new Response(),
          error: undefined,
        };
      }
      if (path === "/tests/{test_id}/answer-layout/detect") {
        if (profile === null) {
          return {
            data: undefined,
            response: new Response(null, { status: 404 }),
            error: { message: "missing layout" },
          };
        }
        const detectResult = input.detectAnswerAreas?.();
        if (detectResult?.kind === "error") {
          return {
            data: undefined,
            response: new Response(null, { status: detectResult.status }),
            error:
              detectResult.retryAfterSeconds === undefined
                ? { detail: detectResult.detail }
                : {
                    detail: {
                      message: detectResult.detail,
                      retry_after_seconds: detectResult.retryAfterSeconds,
                    },
                  },
          };
        }
        profileRevision += 1;
        profile = buildProfile(
          detectResult?.kind === "profile"
            ? {
                status: "draft",
                revision: profileRevision,
                regions: detectResult.profile.regions,
                absent_question_numbers:
                  detectResult.profile.absent_question_numbers,
                undetected_question_numbers:
                  detectResult.profile.undetected_question_numbers,
              }
            : {
                status: "draft",
                revision: profileRevision,
                regions: [],
              },
        );
        return { data: profile, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/criteria/extract") {
        criteriaRevision += 1;
        criteria = {
          test_id: id,
          status: "draft",
          revision: criteriaRevision,
          extracted: true,
          questions: [
            {
              number: "問1",
              points: 10,
              model_answer: "模範解答",
              criteria: [],
              source_pages: [1],
            },
          ],
          declared_total_points: null,
          unreadable_pages: [],
          note: null,
          totals: {
            known_points: 10,
            unknown_count: 0,
            declared_total_points: null,
            declared_difference: null,
            is_complete: true,
          },
        };
        return { data: criteria, response: new Response(), error: undefined };
      }
      return base.POST(path, init);
    }),
    PUT: vi.fn(async (path, init) => {
      if (path === "/tests/{test_id}/criteria") {
        criteriaRevision += 1;
        const body = init?.body as {
          questions: CriteriaResponse["questions"];
          declared_total_points?: number | null;
        };
        criteria = {
          test_id: testId,
          status: "draft",
          revision: criteriaRevision,
          extracted: false,
          questions: body.questions,
          declared_total_points: body.declared_total_points ?? null,
          unreadable_pages: [],
          note: null,
          totals: {
            known_points: 10,
            unknown_count: 0,
            declared_total_points: body.declared_total_points ?? null,
            declared_difference: null,
            is_complete: true,
          },
        };
        return { data: criteria, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/profile") {
        profileRevision += 1;
        const body = init?.body as { regions: ProfileResponse["regions"] };
        profile = buildProfile({
          status: "draft",
          revision: profileRevision,
          regions: body.regions,
        });
        return { data: profile, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/answer-layout") {
        layout = {
          test_id: testId,
          page_count: 1,
          detection_available: true,
          detection_unavailable_reason: null,
          dropped_region_count: 0,
        };
        profileRevision += 1;
        profile = buildProfile({
          status: "draft",
          revision: profileRevision,
          regions: [],
        });
        return { data: layout, response: new Response(), error: undefined };
      }
      return base.PUT(path, init);
    }),
    use: base.use,
  } as unknown as SidecarClient;

  return { client, applyLayoutUpload };
}
