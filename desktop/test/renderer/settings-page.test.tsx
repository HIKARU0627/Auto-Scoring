import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildApiKeySettings,
  buildApiKeyStatus,
  buildVerifyApiKeyResponse,
} from "./support/mock-sidecar-client.js";

const SYNTHETIC_KEY = "fake-openrouter-key-DO-NOT-USE-4c1f9a";

describe("SettingsPage & ApiKeyTab invariants (INV-107 / Issue #249)", () => {
  it("INV-107: API キー未設定なら verify を無効にし、無効の理由を出す", async () => {
    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [buildApiKeyStatus({ configured: false })],
          }),
      },
    });

    // Switch to API キー tab
    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));

    // Status shows "未設定"
    const status = await screen.findByTestId(
      "settings-api-key-status-openrouter",
    );
    expect(status.textContent).toBe("未設定");

    // Verify button is disabled
    const verifyBtn = screen.getByTestId("settings-api-key-verify-openrouter");
    expect(verifyBtn).toHaveProperty("disabled", true);

    // Disabled reason appears with explanation
    const reason = screen.getByTestId("disabled-reason-api-key-not-configured");
    expect(reason).toBeDefined();
    expect(reason.textContent).toContain("キーがまだありません");
    expect(reason.textContent).toContain("保存する");

    // Save button is enabled and has no credential store error
    const saveBtn = screen.getByTestId("settings-api-key-save-openrouter");
    expect(saveBtn).toHaveProperty("disabled", false);
    expect(
      screen.queryByTestId("disabled-reason-credential-store-unavailable"),
    ).toBeNull();
  });

  it("受入条件2: 理由の文言が無効条件そのものから導かれていることの検査", async () => {
    // 1. 未設定時: api-key-not-configured 理由が出る
    const { unmount } = renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [buildApiKeyStatus({ id: "openrouter", configured: false })],
            store_unavailable_reason: null,
          }),
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));
    expect(
      await screen.findByTestId("disabled-reason-api-key-not-configured"),
    ).toBeDefined();
    expect(screen.queryByTestId("disabled-reason-busy")).toBeNull();
    expect(
      screen.queryByTestId("disabled-reason-credential-store-unavailable"),
    ).toBeNull();
    unmount();

    // 2. 資格情報ストア利用不可の要因に変えると、保存ボタンが無効になり別の理由が出る
    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [buildApiKeyStatus({ id: "openrouter", configured: false })],
            store_unavailable_reason: "OSの資格情報ストアを利用できません。",
          }),
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));
    // 保存ボタンが無効で credential-store-unavailable 理由
    const storeReason = await screen.findByTestId(
      "disabled-reason-credential-store-unavailable",
    );
    expect(storeReason.textContent).toContain("環境変数");
    const saveBtn = screen.getByTestId("settings-api-key-save-openrouter");
    expect(saveBtn).toHaveProperty("disabled", true);

    // 疎通ボタンはキー未設定理由のまま (混ざらない)
    const verifyReason = screen.getByTestId(
      "disabled-reason-api-key-not-configured",
    );
    expect(verifyReason).toBeDefined();
  });

  it("条件充足で verify ボタンが有効化され、理由は消去される", async () => {
    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [
              buildApiKeyStatus({
                id: "openrouter",
                configured: true,
                key_source: "credential_store",
              }),
            ],
          }),
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));

    const verifyBtn = await screen.findByTestId(
      "settings-api-key-verify-openrouter",
    );
    expect(verifyBtn).toHaveProperty("disabled", false);
    expect(
      screen.queryByTestId("disabled-reason-api-key-not-configured"),
    ).toBeNull();
    expect(screen.queryByTestId("disabled-reason-busy")).toBeNull();
  });

  it("受入条件3: API キーそのものを画面・ログ・エラー文言に出さない (INV-036)", async () => {
    let savedSlot: string | null = null;
    let savedValue: string | null = null;

    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [buildApiKeyStatus({ configured: false })],
          }),
        saveApiKey: async (slotId, value) => {
          savedSlot = slotId;
          savedValue = value;
          return buildApiKeySettings({
            keys: [
              buildApiKeyStatus({
                id: slotId,
                configured: true,
                key_source: "credential_store",
              }),
            ],
            restart_required: true,
          });
        },
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));

    const input = (await screen.findByTestId(
      "settings-api-key-field-openrouter",
    )) as HTMLInputElement;

    // Type the synthetic key
    fireEvent.change(input, { target: { value: SYNTHETIC_KEY } });
    expect(input.value).toBe(SYNTHETIC_KEY);

    // Save the key
    fireEvent.click(screen.getByTestId("settings-api-key-save-openrouter"));

    await screen.findByTestId("settings-api-key-restart-required");

    // The key was sent via API
    expect(savedSlot).toBe("openrouter");
    expect(savedValue).toBe(SYNTHETIC_KEY);

    // Input field is cleared immediately
    expect(input.value).toBe("");

    // The synthetic key is NOT rendered anywhere in the DOM
    expect(document.body.textContent).not.toContain(SYNTHETIC_KEY);
  });

  it("保存に失敗した際もキーは画面に残らず、エラーメッセージにキーを含めない", async () => {
    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [buildApiKeyStatus({ configured: false })],
          }),
        saveApiKey: async () => {
          throw new Error("資格情報ストアへの書き込みに失敗しました。");
        },
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));

    const input = (await screen.findByTestId(
      "settings-api-key-field-openrouter",
    )) as HTMLInputElement;

    fireEvent.change(input, { target: { value: SYNTHETIC_KEY } });
    fireEvent.click(screen.getByTestId("settings-api-key-save-openrouter"));

    const errorBanner = await screen.findByTestId("settings-api-key-error");
    expect(errorBanner.textContent).toContain(
      "資格情報ストアへの書き込みに失敗しました。",
    );
    // Key cleared from field
    expect(input.value).toBe("");
    // Key not displayed anywhere
    expect(document.body.textContent).not.toContain(SYNTHETIC_KEY);
  });

  it("受入条件4: 生成クライアント経由で疎通確認を実行できる", async () => {
    let verifiedSlot: string | null = null;

    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [
              buildApiKeyStatus({
                id: "openrouter",
                configured: true,
                key_source: "credential_store",
              }),
            ],
          }),
        verifyApiKey: async (slotId) => {
          verifiedSlot = slotId;
          return buildVerifyApiKeyResponse({
            result: "ok",
            detail: "疎通しました。",
          });
        },
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));

    const verifyBtn = await screen.findByTestId(
      "settings-api-key-verify-openrouter",
    );
    fireEvent.click(verifyBtn);

    const verificationResult = await screen.findByTestId(
      "settings-api-key-verification-openrouter",
    );
    expect(verificationResult.textContent).toBe("疎通しました。");
    expect(verifiedSlot).toBe("openrouter");
  });

  it("保存したキーの削除を実行できる", async () => {
    let deletedSlot: string | null = null;

    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [
              buildApiKeyStatus({
                id: "openrouter",
                configured: true,
                key_source: "credential_store",
              }),
            ],
          }),
        deleteApiKey: async (slotId) => {
          deletedSlot = slotId;
          return buildApiKeySettings({
            keys: [buildApiKeyStatus({ id: slotId, configured: false })],
          });
        },
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));

    const deleteBtn = await screen.findByTestId(
      "settings-api-key-delete-openrouter",
    );
    fireEvent.click(deleteBtn);

    const status = await screen.findByTestId(
      "settings-api-key-status-openrouter",
    );
    expect(status.textContent).toBe("未設定");
    expect(deletedSlot).toBe("openrouter");
  });

  it("再起動が必要な場合、通知と再起動ボタンが表示される", async () => {
    const restartMock = vi.fn(async () => {});

    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            restart_required: true,
          }),
      },
      bridge: {
        restartSidecar: restartMock,
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));

    expect(
      await screen.findByTestId("settings-api-key-restart-required"),
    ).toBeDefined();

    const restartBtn = screen.getByTestId("settings-api-key-restart");
    fireEvent.click(restartBtn);

    expect(restartMock).toHaveBeenCalled();
  });

  it("取込の型タブ: 規則の編集と保存ができる", async () => {
    let savedPatterns: string[] = [];

    renderAppAt(AppRoutes.settings, {
      handlers: {
        listIntakeTemplates: async () => [
          {
            id: "default-template",
            name: "標準テンプレート",
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
        ],
        getIntakeCost: async () => ({ classification_unit_cost: null }),
        saveIntakeTemplates: async (templates) => {
          savedPatterns = templates[0]?.rules.map((r) => r.pattern) ?? [];
          return templates;
        },
      },
    });

    // Default tab is 取込の型
    const patternInput = await screen.findByTestId("settings-rule-pattern-0");
    fireEvent.change(patternInput, { target: { value: "answers_*" } });

    // Click save
    fireEvent.click(screen.getByTestId("settings-save"));

    const notice = await screen.findByTestId("settings-saved-notice");
    expect(notice.textContent).toBe("保存しました。次の取込から反映されます。");
    expect(savedPatterns).toEqual(["answers_*"]);
  });

  it("取込の型タブ: 単価は空欄のまま保存できる（0円と偽らない）", async () => {
    let savedCost: number | null | undefined = undefined;

    renderAppAt(AppRoutes.settings, {
      handlers: {
        listIntakeTemplates: async () => [
          {
            id: "default-template",
            name: "標準テンプレート",
            split_child_directories: true,
            rules: [],
          },
        ],
        getIntakeCost: async () => ({ classification_unit_cost: null }),
        saveIntakeCost: async (cost) => {
          savedCost = cost;
          return { classification_unit_cost: cost };
        },
      },
    });

    await screen.findByTestId("settings-unit-cost");
    fireEvent.click(screen.getByTestId("settings-save"));

    await screen.findByTestId("settings-saved-notice");
    expect(savedCost).toBeNull();
  });
});

describe("SettingsPage states (Issue #347, parent #333 §1)", () => {
  it("読み込み中はスケルトンを見せ、内容が届くまでスロットを描かない", async () => {
    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: () => new Promise<never>(() => {}),
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));

    const loading = await screen.findByTestId("settings-api-key-loading");
    expect(loading.getAttribute("aria-busy")).toBe("true");
    expect(loading.querySelector(".animate-pulse")).not.toBeNull();
    // The skeleton must not be replaced by nothing while the request is open.
    expect(
      screen.queryByTestId("settings-api-key-field-openrouter"),
    ).toBeNull();
  });

  it("設定済みと未設定を別の表示で区別する", async () => {
    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [
              buildApiKeyStatus({
                id: "openrouter",
                configured: true,
                key_source: "credential_store",
              }),
              buildApiKeyStatus({ id: "anthropic", configured: false }),
            ],
          }),
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));
    await screen.findByTestId("settings-api-key-status-openrouter");

    const configured = screen
      .getByTestId("settings-api-key-status-openrouter")
      .closest("section");
    const unconfigured = screen
      .getByTestId("settings-api-key-status-anthropic")
      .closest("section");

    expect(configured?.textContent).toContain("設定済み");
    expect(unconfigured?.textContent).toContain("未設定");
    expect(unconfigured?.textContent).not.toContain("設定済み");
  });

  it("提供元が1件も無いときは空の案内を出す", async () => {
    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () => buildApiKeySettings({ keys: [] }),
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));

    const empty = await screen.findByTestId("settings-api-key-empty");
    expect(empty.textContent).toContain("1件も登録されていません");
  });

  it("疎通確認の失敗はエラーとして読める（成功と同じ見た目にしない）", async () => {
    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [
              buildApiKeyStatus({
                configured: true,
                key_source: "credential_store",
              }),
            ],
          }),
        verifyApiKey: async () =>
          buildVerifyApiKeyResponse({
            result: "error",
            detail: "キーが拒否されました。",
            status_code: 401,
          }),
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));
    fireEvent.click(
      await screen.findByTestId("settings-api-key-verify-openrouter"),
    );

    const detail = await screen.findByTestId(
      "settings-api-key-verification-openrouter",
    );
    expect(detail.textContent).toBe("キーが拒否されました。");
    expect(
      screen
        .getByTestId("settings-api-key-verification-card-openrouter")
        .getAttribute("data-tone"),
    ).toBe("error");
  });
});
