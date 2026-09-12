import type { SidecarClient } from "./client.js";
import type { components } from "./generated/schema.js";

export type ApiKeySettingsResponse =
  components["schemas"]["ApiKeySettingsResponse"];
export type ApiKeyStatusModel = components["schemas"]["ApiKeyStatusModel"];
export type TextSettingModel = components["schemas"]["TextSettingModel"];
export type VerifyApiKeyResponse =
  components["schemas"]["VerifyApiKeyResponse"];
export type IntakeTemplateModel = components["schemas"]["IntakeTemplateModel"];
export type IntakeRuleModel = components["schemas"]["IntakeRuleModel"];
export type IntakeCostModel = components["schemas"]["IntakeCostModel"];
export type ConfigurationSource = components["schemas"]["ConfigurationSource"];
export type Requirement = components["schemas"]["Requirement"];
export type RuleScope = components["schemas"]["RuleScope"];
export type MaterialRole = components["schemas"]["MaterialRole"];

export class SettingsDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SettingsDataError";
  }
}

function extractErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === "object" && error !== null) {
    if (
      "detail" in error &&
      typeof (error as { detail?: unknown }).detail === "string"
    ) {
      return (error as { detail: string }).detail;
    }
    if (
      "message" in error &&
      typeof (error as { message?: unknown }).message === "string"
    ) {
      return (error as { message: string }).message;
    }
  }
  return fallback;
}

export async function loadApiKeySettings(
  client: SidecarClient,
): Promise<ApiKeySettingsResponse> {
  const response = await client.GET("/settings/api-keys");
  if (response.data === undefined) {
    throw new SettingsDataError(
      extractErrorMessage(
        (response as { error?: unknown }).error,
        "API キー設定を読み込めませんでした。",
      ),
    );
  }
  return response.data;
}

export async function saveApiKey(
  client: SidecarClient,
  slotId: string,
  value: string,
): Promise<ApiKeySettingsResponse> {
  const response = await client.PUT("/settings/api-keys/{slot_id}", {
    params: { path: { slot_id: slotId } },
    body: { value },
  });
  if (response.data === undefined) {
    throw new SettingsDataError(
      extractErrorMessage(
        (response as { error?: unknown }).error,
        "キーを保存できませんでした。",
      ),
    );
  }
  return response.data;
}

/**
 * Save a slot's non-secret settings (model, GCP project, region) and,
 * optionally, a new key. Values are keyed by environment-variable name; a
 * blank value clears that setting. The key is never returned.
 */
export async function saveProviderSettings(
  client: SidecarClient,
  slotId: string,
  values: Record<string, string | null>,
): Promise<ApiKeySettingsResponse> {
  const response = await client.PUT("/settings/api-keys/{slot_id}", {
    params: { path: { slot_id: slotId } },
    body: { values },
  });
  if (response.data === undefined) {
    throw new SettingsDataError(
      extractErrorMessage(
        (response as { error?: unknown }).error,
        "設定を保存できませんでした。",
      ),
    );
  }
  return response.data;
}

export async function saveTransportOrder(
  client: SidecarClient,
  order: readonly string[],
): Promise<ApiKeySettingsResponse> {
  const response = await client.PUT("/settings/transport-order", {
    body: { order: [...order] },
  });
  if (response.data === undefined) {
    throw new SettingsDataError(
      extractErrorMessage(
        (response as { error?: unknown }).error,
        "使用順序を保存できませんでした。",
      ),
    );
  }
  return response.data;
}

export async function clearTransportOrder(
  client: SidecarClient,
): Promise<ApiKeySettingsResponse> {
  const response = await client.DELETE("/settings/transport-order");
  if (response.data === undefined) {
    throw new SettingsDataError(
      extractErrorMessage(
        (response as { error?: unknown }).error,
        "使用順序を戻せませんでした。",
      ),
    );
  }
  return response.data;
}

export async function deleteApiKey(
  client: SidecarClient,
  slotId: string,
): Promise<ApiKeySettingsResponse> {
  const response = await client.DELETE("/settings/api-keys/{slot_id}", {
    params: { path: { slot_id: slotId } },
  });
  if (response.data === undefined) {
    throw new SettingsDataError(
      extractErrorMessage(
        (response as { error?: unknown }).error,
        "キーを削除できませんでした。",
      ),
    );
  }
  return response.data;
}

export async function verifyApiKey(
  client: SidecarClient,
  slotId: string,
): Promise<VerifyApiKeyResponse> {
  const response = await client.POST("/settings/api-keys/{slot_id}/verify", {
    params: { path: { slot_id: slotId } },
  });
  if (response.data === undefined) {
    throw new SettingsDataError(
      extractErrorMessage(
        (response as { error?: unknown }).error,
        "疎通確認に失敗しました。",
      ),
    );
  }
  return response.data;
}

export async function loadIntakeTemplates(
  client: SidecarClient,
): Promise<IntakeTemplateModel[]> {
  const response = await client.GET("/intake-templates");
  if (response.data === undefined) {
    throw new SettingsDataError("取込の型を取得できません");
  }
  return response.data;
}

export async function saveIntakeTemplates(
  client: SidecarClient,
  templates: IntakeTemplateModel[],
): Promise<IntakeTemplateModel[]> {
  const response = await client.PUT("/intake-templates", {
    body: { templates },
  });
  if (response.data === undefined) {
    throw new SettingsDataError("取込の型の保存に失敗しました");
  }
  return response.data;
}

export async function loadIntakeCost(
  client: SidecarClient,
): Promise<number | null> {
  const response = await client.GET("/intake-cost");
  if (response.data === undefined) {
    throw new SettingsDataError("単価を取得できません");
  }
  return response.data.classification_unit_cost ?? null;
}

export async function saveIntakeCost(
  client: SidecarClient,
  cost: number | null,
): Promise<number | null> {
  const response = await client.PUT("/intake-cost", {
    body: { classification_unit_cost: cost },
  });
  if (response.data === undefined) {
    throw new SettingsDataError("単価の保存に失敗しました");
  }
  return response.data.classification_unit_cost ?? null;
}
