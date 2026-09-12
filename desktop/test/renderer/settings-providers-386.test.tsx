import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildApiKeySettings,
  buildApiKeyStatus,
  buildVerifyApiKeyResponse,
} from "./support/mock-sidecar-client.js";

const OPENAI_KEY = "AUTO_SCORING_OPENAI_API_KEY";

function openAiSlot() {
  return buildApiKeyStatus({
    id: "openai",
    label: "OpenAI",
    transport: "openai",
    key_variable: OPENAI_KEY,
    model: "gpt-4o-mini",
    model_variable: "AUTO_SCORING_OPENAI_MODEL",
    console_url: "https://platform.openai.com/api-keys",
  });
}

function geminiSlot() {
  return buildApiKeyStatus({
    id: "gemini",
    label: "Gemini（Vertex AI）",
    transport: "gemini",
    key_variable: null,
    configured: true,
    model: "gemini-2.5-flash",
    model_variable: "AUTO_SCORING_GEMINI_MODEL",
    host_available: true,
    auth_note:
      "認証は API キーではなく Application Default Credentials（ADC）です。",
    text_settings: [
      {
        variable: "AUTO_SCORING_VERTEX_PROJECT",
        label: "GCP プロジェクト ID",
        value: "",
        source: "none",
        default_value: "",
        placeholder: "my-gcp-project",
        help_text: "省略可。",
      },
      {
        variable: "AUTO_SCORING_VERTEX_LOCATION",
        label: "リージョン",
        value: "global",
        source: "builtin_default",
        default_value: "global",
        placeholder: "global",
        help_text: "省略時は global。",
      },
    ],
  });
}

async function openApiKeyTab(): Promise<void> {
  fireEvent.click(await screen.findByTestId("settings-tab-api-key"));
}

describe("Issue #386: providers, readable settings, and the use order", () => {
  it("shows OpenAI and Gemini; Gemini has Vertex settings but no key field", async () => {
    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({ keys: [openAiSlot(), geminiSlot()] }),
      },
    });
    await openApiKeyTab();

    expect(
      await screen.findByTestId("settings-api-key-field-openai"),
    ).toBeDefined();
    // Vertex AI authenticates with ADC, so there is deliberately no key box.
    expect(screen.queryByTestId("settings-api-key-field-gemini")).toBeNull();
    expect(
      screen.getByTestId(
        "settings-api-key-setting-gemini-AUTO_SCORING_VERTEX_PROJECT",
      ),
    ).toBeDefined();
    expect(
      screen.getByTestId(
        "settings-api-key-setting-gemini-AUTO_SCORING_VERTEX_LOCATION",
      ),
    ).toBeDefined();
    expect(
      screen.getByTestId("settings-api-key-host-gemini").textContent,
    ).toContain("この PC で利用できます");
  });

  it("saves a readable setting keyed by its variable, never the untouched key", async () => {
    let saved: Record<string, string | null> | null = null;
    let savedSlot: string | null = null;

    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({ keys: [openAiSlot()] }),
        saveProviderSettings: async (slotId, values) => {
          savedSlot = slotId;
          saved = values;
          return buildApiKeySettings({
            keys: [
              buildApiKeyStatus({
                id: "openai",
                transport: "openai",
                key_variable: OPENAI_KEY,
                model: "gpt-4.1",
                model_variable: "AUTO_SCORING_OPENAI_MODEL",
                model_source: "credential_store",
              }),
            ],
            restart_required: true,
          });
        },
      },
    });
    await openApiKeyTab();

    const model = (await screen.findByTestId(
      "settings-api-key-model-openai",
    )) as HTMLInputElement;
    fireEvent.change(model, { target: { value: "gpt-4.1" } });
    fireEvent.click(screen.getByTestId("settings-api-key-save-openai"));

    await screen.findByTestId("settings-api-key-restart-required");
    expect(savedSlot).toBe("openai");
    expect(saved).toEqual({ AUTO_SCORING_OPENAI_MODEL: "gpt-4.1" });
    expect(
      await screen.findByTestId("settings-api-key-model-openai"),
    ).toBeDefined();
  });

  it("reorders and saves the use order, and reports it is now stored", async () => {
    let savedOrder: string[] | null = null;

    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [openAiSlot(), geminiSlot()],
            transport_order: "gemini,openai",
            transport_source: "environment",
            transport_order_stored: false,
          }),
        saveTransportOrder: async (order) => {
          savedOrder = order;
          return buildApiKeySettings({
            keys: [openAiSlot(), geminiSlot()],
            transport_order: order.join(","),
            transport_source: "credential_store",
            transport_order_stored: true,
          });
        },
      },
    });
    await openApiKeyTab();

    // Move Gemini below OpenAI.
    fireEvent.click(
      await screen.findByTestId("settings-transport-order-down-gemini"),
    );
    expect(
      screen.getByTestId("settings-api-key-transport-order").textContent,
    ).toBe("openai → gemini");

    fireEvent.click(screen.getByTestId("settings-transport-order-save"));

    await screen.findByTestId("settings-transport-order-revert");
    expect(savedOrder).toEqual(["openai", "gemini"]);
    expect(
      screen.getByTestId("settings-api-key-transport-order").textContent,
    ).toBe("openai → gemini");
  });

  it("reverts a saved order back to the environment", async () => {
    const cleared = vi.fn(async () =>
      buildApiKeySettings({
        keys: [openAiSlot(), geminiSlot()],
        transport_order: "gemini,openai",
        transport_source: "environment",
        transport_order_stored: false,
      }),
    );

    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [openAiSlot(), geminiSlot()],
            transport_order: "openai,gemini",
            transport_source: "credential_store",
            transport_order_stored: true,
          }),
        clearTransportOrder: cleared,
      },
    });
    await openApiKeyTab();

    fireEvent.click(
      await screen.findByTestId("settings-transport-order-revert"),
    );

    expect(cleared).toHaveBeenCalled();
    await screen.findByTestId("settings-api-key-transport-order");
    expect(screen.queryByTestId("settings-transport-order-revert")).toBeNull();
  });

  it("lets a keyless provider be verified without a key", async () => {
    let verifiedSlot: string | null = null;

    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({ keys: [geminiSlot()] }),
        verifyApiKey: async (slotId) => {
          verifiedSlot = slotId;
          return buildVerifyApiKeyResponse({
            result: "ok",
            detail: "ADC を確認できました。",
            key_source: "none",
          });
        },
      },
    });
    await openApiKeyTab();

    const verify = await screen.findByTestId("settings-api-key-verify-gemini");
    expect(verify).toHaveProperty("disabled", false);
    fireEvent.click(verify);

    const result = await screen.findByTestId(
      "settings-api-key-verification-gemini",
    );
    expect(result.textContent).toBe("ADC を確認できました。");
    expect(verifiedSlot).toBe("gemini");
  });

  it("never renders a saved key for the added providers", async () => {
    const secret = "fake-openai-key-DO-NOT-USE-7b2e";

    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({ keys: [openAiSlot()] }),
        saveProviderSettings: async () =>
          buildApiKeySettings({
            keys: [
              buildApiKeyStatus({
                id: "openai",
                transport: "openai",
                key_variable: OPENAI_KEY,
                configured: true,
                key_source: "credential_store",
                model_variable: "AUTO_SCORING_OPENAI_MODEL",
              }),
            ],
            restart_required: true,
          }),
      },
    });
    await openApiKeyTab();

    const input = (await screen.findByTestId(
      "settings-api-key-field-openai",
    )) as HTMLInputElement;
    fireEvent.change(input, { target: { value: secret } });
    fireEvent.click(screen.getByTestId("settings-api-key-save-openai"));

    await screen.findByTestId("settings-api-key-restart-required");
    expect(input.value).toBe("");
    expect(document.body.textContent).not.toContain(secret);
  });
});
