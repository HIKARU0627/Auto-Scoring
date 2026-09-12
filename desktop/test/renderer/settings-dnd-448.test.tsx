import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildApiKeySettings,
  buildApiKeyStatus,
} from "./support/mock-sidecar-client.js";

/**
 * Issue #448: the use order can be reordered by dragging, and the model box
 * suggests ids without becoming a closed list.
 *
 * The two rules these tests exist to protect are: **the arrow buttons stay**
 * (dragging is pointer-only, and the keyboard has to keep working), and **the
 * model stays free text** (a model newer than the suggestion list must still
 * save).
 */

const OPENROUTER_KEY = "AUTO_SCORING_OPENROUTER_API_KEY";
const OPENAI_KEY = "AUTO_SCORING_OPENAI_API_KEY";

function openRouterSlot() {
  return buildApiKeyStatus({
    id: "openrouter",
    label: "OpenRouter",
    transport: "openrouter",
    key_variable: OPENROUTER_KEY,
    model: "google/gemini-2.5-flash",
    model_variable: "AUTO_SCORING_OPENROUTER_MODEL",
    suggested_models: [
      "google/gemini-2.5-flash",
      "anthropic/claude-sonnet-4.5",
    ],
  });
}

function openAiSlot() {
  return buildApiKeyStatus({
    id: "openai",
    label: "OpenAI",
    transport: "openai",
    key_variable: OPENAI_KEY,
    model: "gpt-4o-mini",
    model_variable: "AUTO_SCORING_OPENAI_MODEL",
    suggested_models: ["gpt-4o-mini", "gpt-4.1"],
  });
}

async function openApiKeyTab(): Promise<void> {
  fireEvent.click(await screen.findByTestId("settings-tab-api-key"));
}

function optionsOf(testId: string): string[] {
  return Array.from(screen.getByTestId(testId).querySelectorAll("option")).map(
    (option) => option.value,
  );
}

function renderTwoProviders(transportOrder: string) {
  return renderAppAt(AppRoutes.settings, {
    handlers: {
      getApiKeySettings: async () =>
        buildApiKeySettings({
          keys: [openRouterSlot(), openAiSlot()],
          transport_order: transportOrder,
          transport_source: "environment",
        }),
    },
  });
}

describe("Issue #448: drag-and-drop order and model suggestions", () => {
  it("offers the provider's model ids as datalist suggestions", async () => {
    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({ keys: [openAiSlot()] }),
      },
    });
    await openApiKeyTab();

    const model = (await screen.findByTestId(
      "settings-api-key-model-openai",
    )) as HTMLInputElement;
    expect(model.getAttribute("list")).toBe("api-key-model-options-openai");
    expect(optionsOf("settings-api-key-model-options-openai")).toEqual([
      "gpt-4o-mini",
      "gpt-4.1",
    ]);
  });

  it("keeps the model a free text field: an unlisted id still saves", async () => {
    let saved: Record<string, string | null> | null = null;

    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({ keys: [openAiSlot()] }),
        saveProviderSettings: async (_slotId, values) => {
          saved = values;
          return buildApiKeySettings({
            keys: [openAiSlot()],
            restart_required: true,
          });
        },
      },
    });
    await openApiKeyTab();

    const model = (await screen.findByTestId(
      "settings-api-key-model-openai",
    )) as HTMLInputElement;
    fireEvent.change(model, { target: { value: "gpt-6-not-in-the-list" } });
    fireEvent.click(screen.getByTestId("settings-api-key-save-openai"));

    await screen.findByTestId("settings-api-key-restart-required");
    expect(saved).toEqual({
      AUTO_SCORING_OPENAI_MODEL: "gpt-6-not-in-the-list",
    });
  });

  it("reorders by dragging a handle onto another row", async () => {
    renderTwoProviders("openrouter,openai");
    await openApiKeyTab();

    const handle = await screen.findByTestId(
      "settings-transport-order-handle-openrouter",
    );
    expect(handle.getAttribute("draggable")).toBe("true");

    fireEvent.dragStart(handle, {
      dataTransfer: { effectAllowed: "", setData: () => {} },
    });
    const target = screen.getByTestId("settings-transport-order-item-openai");
    fireEvent.dragOver(target, { dataTransfer: { dropEffect: "" } });
    expect(target.getAttribute("data-drop-target")).toBe("true");
    fireEvent.drop(target, { dataTransfer: {} });

    expect(
      screen.getByTestId("settings-api-key-transport-order").textContent,
    ).toBe("openai → openrouter");
    expect(target.hasAttribute("data-drop-target")).toBe(false);
  });

  it("still reorders with the keyboard via the up/down buttons", async () => {
    renderTwoProviders("openrouter,openai");
    await openApiKeyTab();

    // Keyboard-only path: no drag events at all, just the button.
    fireEvent.click(
      await screen.findByTestId("settings-transport-order-down-openrouter"),
    );
    expect(
      screen.getByTestId("settings-api-key-transport-order").textContent,
    ).toBe("openai → openrouter");

    // And back up again.
    fireEvent.click(
      screen.getByTestId("settings-transport-order-up-openrouter"),
    );
    expect(
      screen.getByTestId("settings-api-key-transport-order").textContent,
    ).toBe("openrouter → openai");
  });

  it("voices the order change for a screen reader", async () => {
    renderTwoProviders("openrouter,openai");
    await openApiKeyTab();

    expect(
      (await screen.findByTestId("settings-transport-order-announcement"))
        .textContent,
    ).toContain("現在の順番: 1. OpenRouter、2. OpenAI");

    fireEvent.click(
      screen.getByTestId("settings-transport-order-down-openrouter"),
    );
    expect(
      screen.getByTestId("settings-transport-order-announcement").textContent,
    ).toContain("現在の順番: 1. OpenAI、2. OpenRouter");
  });
});
