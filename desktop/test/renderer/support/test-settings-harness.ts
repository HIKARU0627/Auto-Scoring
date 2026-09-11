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
const TINY_PNG = Uint8Array.from(
  atob(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  ),
  (char) => char.charCodeAt(0),
);

export function createTestSettingsMockClient(
  input: {
    testId?: string;
    testStatus?: string;
    handlers?: MockSidecarHandlers;
  } = {},
): { client: SidecarClient; applyLayoutUpload: () => AnswerLayoutResponse } {
  const testId = input.testId ?? "t-reg";
  let testStatus = input.testStatus ?? "draft";
  let profile: ProfileResponse | null = null;
  let criteria: CriteriaResponse | null = null;
  let graph: DependencyGraphResponse | null = null;
  let layout: AnswerLayoutResponse = {
    page_count: null,
    detection_available: false,
    detection_unavailable_reason: "E2E stub",
    dropped_region_count: 0,
  };
  let profileRevision = 0;
  let criteriaRevision = 0;
  let graphVersion = 0;
  const questionNumbers: string[] = [];

  const applyLayoutUpload = (): AnswerLayoutResponse => {
    layout = {
      page_count: 1,
      detection_available: false,
      detection_unavailable_reason: "stub",
      dropped_region_count: 0,
    };
    profileRevision += 1;
    profile = {
      status: "draft",
      revision: profileRevision,
      pages: [PAGE],
      regions: [],
      absent_question_numbers: [],
      reading_order_conflicts: [],
    };
    return layout;
  };

  const base = createMockSidecarClient({
    ...input.handlers,
    getTest: async (id) =>
      buildTest({ id, status: testStatus, name: "E2E 理科" }),
  });

  const client: SidecarClient = {
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
      return base.POST(path, init);
    }),
    PUT: vi.fn(async (path, init) => {
      const id = init?.params?.path?.test_id ?? testId;
      if (path === "/tests/{test_id}/criteria") {
        criteriaRevision += 1;
        const body = init?.body as {
          questions: CriteriaResponse["questions"];
          declared_total_points?: number | null;
        };
        criteria = {
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
          },
        };
        return { data: criteria, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/profile") {
        profileRevision += 1;
        const body = init?.body as { regions: ProfileResponse["regions"] };
        profile = {
          status: "draft",
          revision: profileRevision,
          pages: [PAGE],
          regions: body.regions,
          absent_question_numbers: [],
          reading_order_conflicts: [],
        };
        return { data: profile, response: new Response(), error: undefined };
      }
      if (path === "/tests/{test_id}/answer-layout") {
        layout = {
          page_count: 1,
          detection_available: false,
          detection_unavailable_reason: "stub",
          dropped_region_count: 0,
        };
        profileRevision += 1;
        profile = {
          status: "draft",
          revision: profileRevision,
          pages: [PAGE],
          regions: [],
          absent_question_numbers: [],
          reading_order_conflicts: [],
        };
        return { data: layout, response: new Response(), error: undefined };
      }
      return base.PUT(path, init);
    }),
    use: base.use,
  };

  return { client, applyLayoutUpload };
}
