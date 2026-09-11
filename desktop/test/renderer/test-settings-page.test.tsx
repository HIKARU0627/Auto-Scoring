import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { AppRoutes, testSettings } from "../../src/renderer/core/app-routes.js";
import * as answerAreaData from "../../src/renderer/api/answer-area-data.js";
import { renderAppAt } from "./support/app-harness.js";
import { createTestSettingsMockClient } from "./support/test-settings-harness.js";

const VISIBLE_PAGE_IMAGE = {
  objectUrl:
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  pixelWidth: 1190,
  pixelHeight: 1684,
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
      layoutPages: profile?.pages ?? [{ width_pt: 595, height_pt: 842 }],
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
});
