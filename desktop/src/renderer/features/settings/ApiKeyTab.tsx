import { useCallback, useEffect, useState, type JSX } from "react";

import {
  deleteApiKey,
  loadApiKeySettings,
  saveApiKey,
  verifyApiKey,
  SettingsDataError,
  type ApiKeySettingsResponse,
  type ApiKeyStatusModel,
  type VerifyApiKeyResponse,
} from "../../api/settings-data.js";
import {
  loadGradingTokenUnitCost,
  loadMonthlyAiUsage,
  saveGradingTokenUnitCost,
  UsageDataError,
} from "../../core/usage-data.js";
import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
  formatAiUsageDisplay,
  formatProviderAccountBalance,
  type AiUsageNumbers,
} from "../../core/ai-usage-display.js";
import {
  apiKeySaveRequirements,
  apiKeyVerifyRequirements,
} from "../../core/action-requirements.js";
import { AppErrorBanner } from "../../core/AppErrorBanner.js";
import { DisabledActionReason } from "../intake/DisabledActionReason.js";
import {
  NUMERIC_STYLE,
  SETTINGS_BUTTON_DANGER_CLASS,
  SETTINGS_BUTTON_PRIMARY_CLASS,
  SETTINGS_BUTTON_SECONDARY_CLASS,
  SETTINGS_CARD_CLASS,
  SETTINGS_CARD_HEADING_CLASS,
  SETTINGS_ICON_TILE_CLASS,
  SETTINGS_ITEM_HEADING_CLASS,
  SETTINGS_INPUT_CLASS,
  SETTINGS_LABEL_CLASS,
  apiKeyStatePillClass,
  apiKeyVerificationCardClass,
} from "./settings-presentation.js";

function errorText(error: unknown): string {
  return error instanceof SettingsDataError
    ? error.message
    : error instanceof Error
      ? error.message
      : String(error);
}

/**
 * Loading placeholder shaped like the slot cards below it (Issue #347, parent
 * #333 §1 "読み込み中"). The height is close to the real content so the screen
 * does not jump when the settings arrive.
 */
function ApiKeyLoading({ testId }: { testId: string }): JSX.Element {
  return (
    <div
      data-testid={testId}
      aria-busy="true"
      aria-live="polite"
      className="flex flex-col gap-lg"
    >
      <span className="sr-only">設定を読み込んでいます…</span>
      <div className={`${SETTINGS_CARD_CLASS} animate-pulse`}>
        <div className="h-5 w-40 rounded-md bg-surface-container-high" />
        <div className="mt-md h-4 w-3/4 rounded-md bg-surface-container-high" />
        <div className="mt-sm h-4 w-1/2 rounded-md bg-surface-container-high" />
      </div>
      {[0, 1].map((index) => (
        <div key={index} className={`${SETTINGS_CARD_CLASS} animate-pulse`}>
          <div className="flex items-center justify-between">
            <div className="h-5 w-32 rounded-md bg-surface-container-high" />
            <div className="h-6 w-16 rounded-full bg-surface-container-high" />
          </div>
          <div className="mt-md h-10 w-full rounded-md bg-surface-container-high" />
          <div className="mt-md h-9 w-40 rounded-md bg-surface-container-high" />
        </div>
      ))}
    </div>
  );
}

export function ApiKeyTab(): JSX.Element {
  const client = useSidecarClient();

  const [settings, setSettings] = useState<ApiKeySettingsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [busySlotId, setBusySlotId] = useState<string | null>(null);
  const [verified, setVerified] = useState<
    Record<string, VerifyApiKeyResponse>
  >({});
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [restarting, setRestarting] = useState<boolean>(false);
  const [restartError, setRestartError] = useState<string | null>(null);
  const [monthlyUsage, setMonthlyUsage] = useState<AiUsageNumbers | null>(null);
  const [gradingUnitCostInput, setGradingUnitCostInput] = useState<string>("");
  const [gradingCostBusy, setGradingCostBusy] = useState<boolean>(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, monthly, unitCost] = await Promise.all([
        loadApiKeySettings(client),
        loadMonthlyAiUsage(client).catch(() => null),
        loadGradingTokenUnitCost(client).catch(() => null),
      ]);
      setSettings(data);
      setMonthlyUsage(monthly);
      setGradingUnitCostInput(unitCost == null ? "" : String(unitCost));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    void load();
  }, [load]);

  const onInputChange = (slotId: string, value: string) => {
    setInputs((prev) => ({ ...prev, [slotId]: value }));
  };

  const onSave = async (slotId: string) => {
    const value = (inputs[slotId] ?? "").trim();
    if (value.length === 0) {
      setError("API キーを入力してください。");
      return;
    }
    // Clear field immediately so key never sits in the input or leaks
    setInputs((prev) => ({ ...prev, [slotId]: "" }));
    setVerified((prev) => {
      const next = { ...prev };
      delete next[slotId];
      return next;
    });
    setBusySlotId(slotId);
    setError(null);
    try {
      const updated = await saveApiKey(client, slotId, value);
      setSettings(updated);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusySlotId(null);
    }
  };

  const onDelete = async (slotId: string) => {
    setVerified((prev) => {
      const next = { ...prev };
      delete next[slotId];
      return next;
    });
    setBusySlotId(slotId);
    setError(null);
    try {
      const updated = await deleteApiKey(client, slotId);
      setSettings(updated);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusySlotId(null);
    }
  };

  const onVerify = async (slotId: string) => {
    setBusySlotId(slotId);
    setError(null);
    setVerified((prev) => {
      const next = { ...prev };
      delete next[slotId];
      return next;
    });
    try {
      const outcome = await verifyApiKey(client, slotId);
      setVerified((prev) => ({ ...prev, [slotId]: outcome }));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusySlotId(null);
    }
  };

  const onRestart = async () => {
    setRestarting(true);
    setRestartError(null);
    try {
      if (typeof window.autoScoring?.restartSidecar === "function") {
        await window.autoScoring.restartSidecar();
      } else {
        setRestartError(
          "この起動方法では画面から再起動できません。アプリを起動し直してください。",
        );
      }
    } catch (err) {
      setRestartError(
        err instanceof Error ? err.message : "再起動に失敗しました。",
      );
    } finally {
      setRestarting(false);
    }
  };

  if (loading) {
    return <ApiKeyLoading testId="settings-api-key-loading" />;
  }

  if (settings === null) {
    return (
      <AppErrorBanner
        testId="settings-api-key-error"
        message={`API キーの設定を読み込めませんでした: ${error ?? "原因は分かりません"}`}
        onRetry={() => {
          void load();
        }}
      />
    );
  }

  const canSave = settings.store_unavailable_reason == null;
  const monthlyDisplay =
    monthlyUsage != null ? formatAiUsageDisplay(monthlyUsage) : null;

  const onSaveGradingUnitCost = async () => {
    const trimmed = gradingUnitCostInput.trim();
    const parsed = trimmed.length === 0 ? null : Number.parseFloat(trimmed);
    if (trimmed.length > 0 && !Number.isFinite(parsed)) {
      setError("1000トークンあたりの単価は数字で入力してください。");
      return;
    }
    setGradingCostBusy(true);
    setError(null);
    try {
      const saved = await saveGradingTokenUnitCost(client, parsed);
      setGradingUnitCostInput(saved == null ? "" : String(saved));
      const monthly = await loadMonthlyAiUsage(client);
      setMonthlyUsage(monthly);
    } catch (err) {
      setError(
        err instanceof UsageDataError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setGradingCostBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-lg">
      <section className={SETTINGS_CARD_CLASS}>
        <h2 className={SETTINGS_CARD_HEADING_CLASS}>AI 採点に使うキー</h2>
        <p className="mt-xs text-body-medium text-on-surface-variant">
          AI
          採点は外部のサービスに問い合わせます。その利用料は、ここに入れたキーの持ち主に請求されます。
        </p>
        <p className="mt-xs text-body-medium text-on-surface-variant">
          キーはこの PC の資格情報ストアに保存し、画面には二度と表示しません。
        </p>
      </section>

      {settings.store_unavailable_reason ? (
        <div
          data-testid="settings-api-key-store-unavailable"
          className="rounded-xl bg-error-container px-lg py-md text-on-error-container"
        >
          <p className="text-body-medium">
            {settings.store_unavailable_reason}
            {
              " キーの保存はできません。環境変数で渡す運用は今までどおり使えます。"
            }
          </p>
        </div>
      ) : null}

      {error ? (
        <AppErrorBanner
          testId="settings-api-key-error"
          message={error}
          retryable={false}
        />
      ) : null}

      {settings.restart_required ? (
        <div className="rounded-xl bg-attention-container/40 px-lg py-md text-on-attention-container">
          <p
            data-testid="settings-api-key-restart-required"
            className="text-body-medium"
          >
            保存した内容は、まだ採点には使われていません。反映するにはサイドカーを再起動します。
          </p>
          {restartError ? (
            <p className="mt-xs text-xs text-error">{restartError}</p>
          ) : null}
          {typeof window.autoScoring?.restartSidecar === "function" ? (
            <div className="mt-sm">
              <button
                type="button"
                data-testid="settings-api-key-restart"
                onClick={onRestart}
                disabled={restarting}
                className={SETTINGS_BUTTON_PRIMARY_CLASS}
              >
                {restarting ? "再起動中…" : "いま再起動して反映する"}
              </button>
            </div>
          ) : (
            <p className="mt-xs text-xs">
              この起動方法では画面から再起動できません。アプリを起動し直してください。
            </p>
          )}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-lg lg:grid-cols-3">
        <div className="flex flex-col gap-lg lg:col-span-2">
          {settings.keys.length === 0 ? (
            <section className={SETTINGS_CARD_CLASS}>
              <div className="flex items-start gap-md">
                <span aria-hidden className={SETTINGS_ICON_TILE_CLASS}>
                  +
                </span>
                <div className="min-w-0 flex-1">
                  <h2 className={SETTINGS_CARD_HEADING_CLASS}>提供元</h2>
                  <p
                    data-testid="settings-api-key-empty"
                    className="mt-xs text-body-medium text-on-surface-variant"
                  >
                    提供元が1件も登録されていません。アプリを更新すると既定の提供元が並びます。
                  </p>
                </div>
              </div>
            </section>
          ) : null}

          <div className="flex flex-col gap-lg">
            {settings.keys.map((slot: ApiKeyStatusModel) => {
              const isBusy = busySlotId === slot.id;
              const saveReqs = apiKeySaveRequirements({
                busy: isBusy,
                credentialStoreAvailable: canSave,
              });
              const verifyReqs = apiKeyVerifyRequirements({
                busy: isBusy,
                configured: slot.configured,
              });
              const verification = verified[slot.id];

              const statusText =
                slot.configured && slot.key_source === "credential_store"
                  ? "保存済み（この PC の資格情報ストア）"
                  : slot.configured
                    ? `環境変数 ${slot.key_variable} から読み込み済み`
                    : "未設定";

              return (
                <section key={slot.id} className={SETTINGS_CARD_CLASS}>
                  <div className="flex flex-wrap items-center justify-between gap-sm">
                    <h3 className={SETTINGS_ITEM_HEADING_CLASS}>
                      {slot.label}
                    </h3>
                    <span className={apiKeyStatePillClass(slot.configured)}>
                      <span aria-hidden>{slot.configured ? "✓" : "−"}</span>
                      {slot.configured ? "設定済み" : "未設定"}
                    </span>
                  </div>
                  <p
                    data-testid={`settings-api-key-status-${slot.id}`}
                    className="mt-xs text-body-medium text-on-surface-variant"
                  >
                    {statusText}
                  </p>
                  <p className="mt-xs text-xs text-on-surface-variant">
                    {`モデル: ${slot.model}${
                      slot.model_source === "environment"
                        ? "（環境変数）"
                        : "（既定）"
                    }`}
                  </p>
                  <p className="mt-xs select-text text-xs text-on-surface-variant">
                    {`キーの発行: ${slot.console_url}`}
                  </p>

                  <div className="mt-md">
                    <label
                      htmlFor={`api-key-${slot.id}`}
                      className={SETTINGS_LABEL_CLASS}
                    >
                      {slot.configured ? "新しいキーに置き換える" : "API キー"}
                    </label>
                    <input
                      id={`api-key-${slot.id}`}
                      data-testid={`settings-api-key-field-${slot.id}`}
                      type="password"
                      autoComplete="new-password"
                      placeholder="•••• •••• ••••"
                      value={inputs[slot.id] ?? ""}
                      onChange={(e) => onInputChange(slot.id, e.target.value)}
                      className={SETTINGS_INPUT_CLASS}
                    />
                    {canSave ? (
                      <p className="mt-xs text-xs text-on-surface-variant">
                        保存すると、この欄は空になります。保存したキーは表示できません。
                      </p>
                    ) : null}
                  </div>

                  <div className="mt-md flex flex-wrap items-center gap-sm">
                    <button
                      type="button"
                      data-testid={`settings-api-key-save-${slot.id}`}
                      onClick={() => void onSave(slot.id)}
                      disabled={saveReqs.length > 0}
                      className={SETTINGS_BUTTON_PRIMARY_CLASS}
                    >
                      {isBusy ? "処理中…" : "保存する"}
                    </button>
                    <button
                      type="button"
                      data-testid={`settings-api-key-verify-${slot.id}`}
                      onClick={() => void onVerify(slot.id)}
                      disabled={verifyReqs.length > 0}
                      className={SETTINGS_BUTTON_SECONDARY_CLASS}
                    >
                      疎通を確認する
                    </button>
                    {slot.configured &&
                    slot.key_source === "credential_store" ? (
                      <button
                        type="button"
                        data-testid={`settings-api-key-delete-${slot.id}`}
                        onClick={() => void onDelete(slot.id)}
                        disabled={busySlotId !== null}
                        className={SETTINGS_BUTTON_DANGER_CLASS}
                      >
                        保存したキーを削除する
                      </button>
                    ) : null}
                  </div>

                  <DisabledActionReason requirements={saveReqs} />
                  <DisabledActionReason requirements={verifyReqs} />

                  {verification ? (
                    <div
                      data-testid={`settings-api-key-verification-card-${slot.id}`}
                      data-tone={
                        verification.result === "ok" ? "success" : "error"
                      }
                      className={apiKeyVerificationCardClass(
                        verification.result === "ok",
                      )}
                    >
                      <span aria-hidden className="shrink-0 text-body-medium">
                        {verification.result === "ok" ? "✓" : "!"}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p
                          data-testid={`settings-api-key-verification-${slot.id}`}
                          className="text-body-medium"
                        >
                          {verification.detail}
                        </p>
                        {formatProviderAccountBalance(
                          verification.provider_account_usage,
                          verification.provider_account_limit,
                        ) != null ? (
                          <p
                            data-testid={`settings-api-key-provider-balance-${slot.id}`}
                            className="text-xs"
                            style={NUMERIC_STYLE}
                          >
                            {formatProviderAccountBalance(
                              verification.provider_account_usage,
                              verification.provider_account_limit,
                            )}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </section>
              );
            })}
          </div>
        </div>
        <div className="flex flex-col gap-lg">
          <section
            data-testid="settings-monthly-ai-usage"
            className={SETTINGS_CARD_CLASS}
          >
            <h2 className={SETTINGS_CARD_HEADING_CLASS}>
              今月の AI 採点（このアプリの積算）
            </h2>
            {monthlyDisplay != null ? (
              <div className="mt-sm flex flex-col gap-xs">
                <p
                  data-testid="settings-monthly-ai-usage-tokens"
                  className="text-body-medium text-on-surface"
                  style={NUMERIC_STYLE}
                >
                  {monthlyDisplay.tokenLine}
                </p>
                {monthlyDisplay.costLine != null ? (
                  <p
                    data-testid="settings-monthly-ai-usage-cost"
                    className="text-body-medium text-on-surface"
                    style={NUMERIC_STYLE}
                  >
                    {monthlyDisplay.costLine}
                  </p>
                ) : null}
              </div>
            ) : (
              <div
                data-testid="settings-monthly-ai-usage-unavailable"
                className="mt-sm text-body-medium text-on-surface-variant"
              >
                今月の利用量を取得できませんでした。「再読み込み」でもう一度試せます。
              </div>
            )}
            <div className="mt-lg">
              <label
                htmlFor="grading-token-unit-cost"
                className={SETTINGS_LABEL_CLASS}
              >
                採点 1000 トークンあたりの単価
              </label>
              <input
                id="grading-token-unit-cost"
                data-testid="settings-grading-unit-cost"
                type="text"
                inputMode="decimal"
                value={gradingUnitCostInput}
                onChange={(event) =>
                  setGradingUnitCostInput(event.target.value)
                }
                className={`${SETTINGS_INPUT_CLASS} max-w-80`}
                style={NUMERIC_STYLE}
              />
              <p className="mt-xs text-xs text-on-surface-variant">
                空欄のままなら金額は出さず、トークン数だけ表示します。
              </p>
              <button
                type="button"
                data-testid="settings-grading-unit-cost-save"
                disabled={gradingCostBusy}
                onClick={() => void onSaveGradingUnitCost()}
                className={`${SETTINGS_BUTTON_PRIMARY_CLASS} mt-sm`}
              >
                {gradingCostBusy ? "保存中…" : "単価を保存"}
              </button>
            </div>
          </section>

          <section className={SETTINGS_CARD_CLASS}>
            <h2 className={SETTINGS_CARD_HEADING_CLASS}>使う順番</h2>
            <p
              data-testid="settings-api-key-transport-order"
              className="mt-xs text-body-medium text-on-surface"
            >
              {settings.transport_order.length > 0
                ? settings.transport_order
                : "（まだありません）"}
            </p>
            <p className="mt-xs text-xs text-on-surface-variant">
              {settings.transport_source === "environment"
                ? "この PC の環境変数 AUTO_SCORING_AI_GRADING_TRANSPORT で決まっています。ここでキーを足しても、この順番は変わりません。"
                : settings.transport_source === "builtin_default"
                  ? "保存されているキーから決めています。"
                  : "キーも環境変数もまだありません。"}
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
