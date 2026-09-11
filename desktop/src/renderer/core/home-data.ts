import type { SidecarClient } from "../api/client.js";
import { HomeDashboard } from "./home-dashboard.js";

export class HomeDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HomeDataError";
  }
}

/**
 * Loads every test registration and all of their submissions for the home
 * dashboard. Uses the generated OpenAPI client only — no hand-written fetch.
 */
export async function loadHomeDashboard(
  client: SidecarClient,
): Promise<HomeDashboard> {
  const registrations = await client.GET("/test-registrations");
  if (registrations.error !== undefined) {
    throw new HomeDataError("作業状況を取得できません");
  }

  const tests = registrations.data;
  const submissionsByTestId: Record<
    string,
    readonly import("./home-dashboard.js").SubmissionResponse[]
  > = {};

  const submissionLists = await Promise.all(
    tests.map(async (test) => {
      const response = await client.GET("/tests/{test_id}/submissions", {
        params: { path: { test_id: test.id } },
      });
      if (response.error !== undefined) {
        throw new HomeDataError("作業状況を取得できません");
      }
      return response.data;
    }),
  );

  for (const [index, test] of tests.entries()) {
    submissionsByTestId[test.id] = submissionLists[index] ?? [];
  }

  return HomeDashboard.from({ tests, submissionsByTestId });
}
