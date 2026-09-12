import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { testSettings } from "../../src/renderer/core/app-routes.js";
import * as answerAreaData from "../../src/renderer/api/answer-area-data.js";
import { renderAppAt } from "./support/app-harness.js";
import { createTestSettingsMockClient } from "./support/test-settings-harness.js";

const VISIBLE_PAGE_IMAGE = {
  objectUrl:
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  pixelWidth: 1190,
  pixelHeight: 1684,
} as const;
const LAYOUT_PAGE = {
  page_index: 0,
  displayed_width: 595,
  displayed_height: 842,
  rotation: 0,
} as const;

/** Same stand-in as `test-settings-page.test.tsx`: the real editor load wants
 * image blobs the mock client does not serve. */
vi.spyOn(answerAreaData, "loadAnswerAreaEditorData").mockImplementation(
  async (client, testId) => {
    const [profileResult, layoutResult] = await Promise.all([
      client.GET("/tests/{test_id}/profile", {
        params: { path: { test_id: testId } },
      }),
      client.GET("/tests/{test_id}/answer-layout", {
        params: { path: { test_id: testId } },
      }),
    ]);
    const profile =
      profileResult.error === undefined ? profileResult.data : null;
    const layout = layoutResult.error === undefined ? layoutResult.data : null;
    const pageCount = profile?.pages.length ?? layout?.page_count ?? 0;
    return {
      profile,
      layout,
      pageImages: Array.from({ length: pageCount }, () => VISIBLE_PAGE_IMAGE),
      layoutPages: profile?.pages
        ? profile.pages.map((page, page_index) => ({
            page_index,
            displayed_width: page.width_pt,
            displayed_height: page.height_pt,
            rotation: 0,
          }))
        : [LAYOUT_PAGE],
    };
  },
);

/**
 * Issue #424: テスト設定の「同じ理由が 2 回出る」「済んだ条件を残りに数える」。
 *
 * The duplicates came from rendering the same `ActionRequirement.id` through
 * more than one list, not from the wording. These tests read the rendered
 * test ids rather than the source, so they fail on the symptom the reviewer
 * saw and pass only when each id is on screen at most once.
 */
function renderedRequirementIds(): readonly string[] {
  const reasonIds = screen
    .queryAllByTestId(/^disabled-reason-/)
    .map((node) =>
      (node.getAttribute("data-testid") ?? "").replace("disabled-reason-", ""),
    );
  const remainingIds = screen
    .queryAllByTestId(/^remaining-work-/)
    .map((node) => node.getAttribute("data-testid") ?? "")
    .filter(
      (testId) =>
        testId !== "remaining-work-label" && testId !== "remaining-work-count",
    )
    .map((testId) => testId.replace("remaining-work-", ""));
  return [...reasonIds, ...remainingIds];
}

describe("テスト設定の無効理由は 2 度出さない (Issue #424)", () => {
  it("確定済みプロファイルの理由を、ボタンごとに繰り返さない", async () => {
    const { client } = createTestSettingsMockClient({
      seed: "confirmed-profile",
    });
    renderAppAt(testSettings("t-reg"), { client });

    await screen.findByTestId("profile-section");

    const occurrences = renderedRequirementIds().filter(
      (id) => id === "profile-already-confirmed",
    );
    expect(occurrences).toHaveLength(1);
  });

  it("同じ理由 id を画面全体で 1 回しか描かない", async () => {
    const { client } = createTestSettingsMockClient({
      seed: "confirmed-profile",
    });
    renderAppAt(testSettings("t-reg"), { client });

    await screen.findByTestId("profile-section");

    const ids = renderedRequirementIds();
    const duplicated = ids.filter((id, index) => ids.indexOf(id) !== index);
    expect(duplicated).toEqual([]);
  });
});

describe("「残りの確認」は未達のものだけを数える (Issue #424)", () => {
  it("未達の理由を「残りの確認」と無効理由の両方に二重に描かない", async () => {
    const { client } = createTestSettingsMockClient();
    renderAppAt(testSettings("t-reg"), { client });

    await screen.findByTestId("complete-registration-section");

    const ids = renderedRequirementIds();
    expect(ids).toContain("profile-unconfirmed");
    const duplicated = ids.filter((id, index) => ids.indexOf(id) !== index);
    expect(duplicated).toEqual([]);
  });

  it("登録完了済みの理由を残りに数えず、その説明は 1 回だけ出す", async () => {
    const { client } = createTestSettingsMockClient({
      testStatus: "ready",
      seed: "confirmed-registration",
    });
    renderAppAt(testSettings("t-reg"), { client });

    await screen.findByTestId("complete-registration-section");

    expect(screen.getByTestId("remaining-work-count").textContent).toBe(
      "残りの確認はありません",
    );
    expect(
      screen.queryByTestId("remaining-work-registration-already-complete"),
    ).toBeNull();
    expect(
      screen.getAllByTestId("disabled-reason-registration-already-complete"),
    ).toHaveLength(1);
  });
});
