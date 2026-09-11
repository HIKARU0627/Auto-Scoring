import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { ActionRequirements } from "../../src/renderer/core/action-requirements.js";
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

describe("TestSettingsPage registration flow", () => {
  it("walks criteria → profile → dependency graph → complete registration", async () => {
    const { client, applyLayoutUpload } = createTestSettingsMockClient();
    renderAppAt(testSettings("t-reg"), {
      client,
      bridge: {
        choosePdfFile: async () => "/tmp/answer.pdf",
        sidecarMultipartUpload: async () => ({
          status: 200,
          body: applyLayoutUpload(),
        }),
      },
    });

    await screen.findByTestId("criteria-section");
    fireEvent.click(screen.getByTestId("add-criteria-question-button"));
    fireEvent.change(screen.getByTestId("criteria-number-0"), {
      target: { value: "問1" },
    });
    fireEvent.change(screen.getByTestId("criteria-points-0"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByTestId("criteria-model-answer-0"), {
      target: { value: "模範解答" },
    });
    fireEvent.click(screen.getByTestId("confirm-criteria-button"));
    await waitFor(() => {
      expect(screen.getByTestId("confirm-criteria-button")).toHaveProperty(
        "disabled",
        true,
      );
    });

    fireEvent.click(screen.getByTestId("upload-answer-layout-button"));
    await screen.findByTestId("answer-area-editor");
    fireEvent.click(screen.getByTestId("add-region-button"));
    fireEvent.click(screen.getByTestId("confirm-profile-button"));
    await waitFor(() => {
      expect(screen.getByTestId("confirm-profile-button")).toHaveProperty(
        "disabled",
        true,
      );
    });

    fireEvent.click(screen.getByTestId("analyze-dependency-graph-button"));
    await screen.findByTestId("dependency-graph-empty");
    fireEvent.click(screen.getByTestId("confirm-dependency-graph-button"));
    await waitFor(() => {
      expect(
        screen.getByTestId("confirm-dependency-graph-button"),
      ).toHaveProperty("disabled", true);
    });

    fireEvent.click(screen.getByTestId("complete-registration-button"));
    await screen.findByText("テスト状態: 登録完了");
    await waitFor(() => {
      expect(screen.getByTestId("complete-registration-button")).toHaveProperty(
        "disabled",
        true,
      );
    });
  });

  it("shows disabled reasons instead of silently blocking confirm", async () => {
    const { client } = createTestSettingsMockClient();
    renderAppAt(testSettings("t-reg"), {
      client,
    });
    await screen.findByTestId("profile-section");
    expect(screen.getByTestId("confirm-profile-button")).toHaveProperty(
      "disabled",
      true,
    );
    expect(
      screen.getByTestId("disabled-reason-answer-regions-missing"),
    ).toBeDefined();
  });

  it("opens the extract cost dialog and applies a stubbed extraction", async () => {
    const { client } = createTestSettingsMockClient();
    renderAppAt(testSettings("t-reg"), { client });
    await screen.findByTestId("criteria-section");

    fireEvent.click(screen.getByTestId("extract-criteria-button"));
    await screen.findByTestId("extract-confirm-dialog");
    expect(screen.getByTestId("extract-page-count").textContent).toContain(
      "1 ページ",
    );

    fireEvent.click(screen.getByTestId("extract-confirm-button"));
    await waitFor(() => {
      expect(screen.queryByTestId("extract-confirm-dialog")).toBeNull();
    });
    expect(
      (screen.getByTestId("criteria-number-0") as HTMLInputElement).value,
    ).toBe("問1");
  });

  it("keeps add-region enabled and shows reasons after zero-result detection", async () => {
    const { client, applyLayoutUpload } = createTestSettingsMockClient();
    renderAppAt(testSettings("t-reg"), {
      client,
      bridge: {
        choosePdfFile: async () => "/tmp/answer.pdf",
        sidecarMultipartUpload: async () => ({
          status: 200,
          body: applyLayoutUpload(),
        }),
      },
    });

    await screen.findByTestId("criteria-section");
    fireEvent.click(screen.getByTestId("add-criteria-question-button"));
    fireEvent.change(screen.getByTestId("criteria-number-0"), {
      target: { value: "問1" },
    });
    fireEvent.change(screen.getByTestId("criteria-points-0"), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByTestId("confirm-criteria-button"));
    await waitFor(() => {
      expect(screen.getByTestId("confirm-criteria-button")).toHaveProperty(
        "disabled",
        true,
      );
    });

    fireEvent.click(screen.getByTestId("upload-answer-layout-button"));
    await screen.findByTestId("answer-area-editor");
    expect(screen.getByTestId("add-region-button")).toHaveProperty(
      "disabled",
      false,
    );

    fireEvent.click(screen.getByTestId("detect-answer-areas-button"));
    await waitFor(() => {
      expect(screen.getByTestId("answer-detection-outcome")).toBeDefined();
    });

    expect(screen.getByTestId("add-region-button")).toHaveProperty(
      "disabled",
      false,
    );
    expect(screen.getByTestId("confirm-profile-button")).toHaveProperty(
      "disabled",
      true,
    );
    expect(
      screen.getByTestId("disabled-reason-answer-detection-zero-results")
        .textContent,
    ).toBe(ActionRequirements.answerDetectionZeroResults.message);
    expect(
      screen.getByTestId("disabled-reason-answer-regions-missing").textContent,
    ).toBe(ActionRequirements.answerRegionsMissing.message);
  });

  it("shows role-mismatch guidance when every question is absent on the sheet", async () => {
    const { client, applyLayoutUpload } = createTestSettingsMockClient({
      detectAnswerAreas: () => ({
        kind: "profile",
        profile: {
          test_id: "t-reg",
          status: "draft",
          revision: 2,
          regions: [],
          question_numbers: ["問1"],
          unassigned_region_ids: [],
          undetected_question_numbers: [],
          absent_question_numbers: ["問1"],
          reading_order_conflicts: [],
          pages: [{ width_pt: 595, height_pt: 842 }],
        },
      }),
    });

    renderAppAt(testSettings("t-reg"), {
      client,
      bridge: {
        choosePdfFile: async () => "/tmp/answer.pdf",
        sidecarMultipartUpload: async () => ({
          status: 200,
          body: applyLayoutUpload(),
        }),
      },
    });

    await screen.findByTestId("criteria-section");
    fireEvent.click(screen.getByTestId("add-criteria-question-button"));
    fireEvent.change(screen.getByTestId("criteria-number-0"), {
      target: { value: "問1" },
    });
    fireEvent.change(screen.getByTestId("criteria-points-0"), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByTestId("confirm-criteria-button"));
    await waitFor(() => {
      expect(screen.getByTestId("confirm-criteria-button")).toHaveProperty(
        "disabled",
        true,
      );
    });

    fireEvent.click(screen.getByTestId("upload-answer-layout-button"));
    await screen.findByTestId("answer-area-editor");
    fireEvent.click(screen.getByTestId("detect-answer-areas-button"));
    await waitFor(() => {
      expect(
        screen.getByTestId("disabled-reason-answer-sheet-role-mismatch"),
      ).toBeDefined();
    });
    expect(
      screen.getByTestId("disabled-reason-answer-sheet-role-mismatch")
        .textContent,
    ).toBe(ActionRequirements.answerSheetRoleMismatch.message);
  });

  it("shows detection failure in the action error banner", async () => {
    const { client, applyLayoutUpload } = createTestSettingsMockClient({
      detectAnswerAreas: () => ({
        kind: "error",
        status: 503,
        detail: "provider unavailable",
      }),
    });

    renderAppAt(testSettings("t-reg"), {
      client,
      bridge: {
        choosePdfFile: async () => "/tmp/answer.pdf",
        sidecarMultipartUpload: async () => ({
          status: 200,
          body: applyLayoutUpload(),
        }),
      },
    });

    await screen.findByTestId("criteria-section");
    fireEvent.click(screen.getByTestId("add-criteria-question-button"));
    fireEvent.change(screen.getByTestId("criteria-number-0"), {
      target: { value: "問1" },
    });
    fireEvent.change(screen.getByTestId("criteria-points-0"), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByTestId("confirm-criteria-button"));
    await waitFor(() => {
      expect(screen.getByTestId("confirm-criteria-button")).toHaveProperty(
        "disabled",
        true,
      );
    });

    fireEvent.click(screen.getByTestId("upload-answer-layout-button"));
    await screen.findByTestId("answer-area-editor");
    fireEvent.click(screen.getByTestId("detect-answer-areas-button"));
    await waitFor(() => {
      expect(screen.getByTestId("test-settings-action-error")).toBeDefined();
    });
    expect(
      screen.getByTestId("test-settings-action-error").textContent,
    ).toContain("provider unavailable");
  });

  it("shows the single-source wait guidance for a rate-limited detection (Issue #304)", async () => {
    const { client, applyLayoutUpload } = createTestSettingsMockClient({
      detectAnswerAreas: () => ({
        kind: "error",
        status: 503,
        detail: "Vertex AI request failed with status 429",
        retryAfterSeconds: 30,
      }),
    });

    renderAppAt(testSettings("t-reg"), {
      client,
      bridge: {
        choosePdfFile: async () => "/tmp/answer.pdf",
        sidecarMultipartUpload: async () => ({
          status: 200,
          body: applyLayoutUpload(),
        }),
      },
    });

    await screen.findByTestId("criteria-section");
    fireEvent.click(screen.getByTestId("add-criteria-question-button"));
    fireEvent.change(screen.getByTestId("criteria-number-0"), {
      target: { value: "問1" },
    });
    fireEvent.change(screen.getByTestId("criteria-points-0"), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByTestId("confirm-criteria-button"));
    await waitFor(() => {
      expect(screen.getByTestId("confirm-criteria-button")).toHaveProperty(
        "disabled",
        true,
      );
    });

    fireEvent.click(screen.getByTestId("upload-answer-layout-button"));
    await screen.findByTestId("answer-area-editor");
    fireEvent.click(screen.getByTestId("detect-answer-areas-button"));

    await waitFor(() => {
      expect(
        screen.getByTestId("disabled-reason-answer-detection-rate-limited"),
      ).toBeDefined();
    });
    expect(
      screen.getByTestId("disabled-reason-answer-detection-rate-limited")
        .textContent,
    ).toBe(ActionRequirements.answerDetectionRateLimited(30).message);
    // The provider's own English must never reach the screen, and the
    // rate-limited guidance is the outcome message rather than the generic
    // error banner.
    expect(
      screen.queryByText(/Vertex AI request failed with status 429/),
    ).toBeNull();
    expect(screen.queryByTestId("test-settings-action-error")).toBeNull();
  });

  it("never leaves two disabled profile actions without visible reasons", async () => {
    const { client, applyLayoutUpload } = createTestSettingsMockClient();
    renderAppAt(testSettings("t-reg"), {
      client,
      bridge: {
        choosePdfFile: async () => "/tmp/answer.pdf",
        sidecarMultipartUpload: async () => ({
          status: 200,
          body: applyLayoutUpload(),
        }),
      },
    });

    await screen.findByTestId("criteria-section");
    fireEvent.click(screen.getByTestId("add-criteria-question-button"));
    fireEvent.change(screen.getByTestId("criteria-number-0"), {
      target: { value: "問1" },
    });
    fireEvent.change(screen.getByTestId("criteria-points-0"), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByTestId("confirm-criteria-button"));
    await waitFor(() => {
      expect(screen.getByTestId("confirm-criteria-button")).toHaveProperty(
        "disabled",
        true,
      );
    });

    fireEvent.click(screen.getByTestId("upload-answer-layout-button"));
    await screen.findByTestId("answer-area-editor");
    fireEvent.click(screen.getByTestId("detect-answer-areas-button"));
    await waitFor(() => {
      expect(screen.getByTestId("confirm-profile-button")).toHaveProperty(
        "disabled",
        true,
      );
    });

    const disabledButtons = ["add-region-button", "confirm-profile-button"]
      .map((id) => screen.getByTestId(id))
      .filter((button) => (button as HTMLButtonElement).disabled);
    const visibleReasons = screen
      .getAllByTestId(/^disabled-reason-/)
      .map((node) => node.getAttribute("data-testid"));

    expect(disabledButtons.length).toBeGreaterThan(0);
    expect(visibleReasons.length).toBeGreaterThanOrEqual(
      disabledButtons.length,
    );
  });

  it("closes the extract cost dialog when cancel is pressed", async () => {
    const { client } = createTestSettingsMockClient();
    renderAppAt(testSettings("t-reg"), { client });
    await screen.findByTestId("criteria-section");

    fireEvent.click(screen.getByTestId("extract-criteria-button"));
    await screen.findByTestId("extract-confirm-dialog");
    fireEvent.click(screen.getByTestId("extract-cancel-button"));

    await waitFor(() => {
      expect(screen.queryByTestId("extract-confirm-dialog")).toBeNull();
    });
    expect(screen.getByTestId("extract-criteria-button")).toHaveProperty(
      "disabled",
      false,
    );
  });
});
