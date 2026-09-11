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
import { DisabledActionReason } from "../intake/DisabledActionReason.js";

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
      setError(
        err instanceof SettingsDataError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err),
      );
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
      setError(
        err instanceof SettingsDataError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err),
      );
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
      setError(
        err instanceof SettingsDataError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err),
      );
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
      setError(
        err instanceof SettingsDataError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err),
      );
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
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-body-medium text-on-surface-variant">読み込み中…</p>
      </div>
    );
  }

  if (settings === null) {
    return (
      <div className="flex flex-col gap-md">
        <div
          data-testid="settings-api-key-error"
          className="rounded-md border border-error bg-error-container p-md text-on-error-container"
        >
          <p className="text-body-medium">
            {error ?? "設定を読み込めませんでした。"}
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="self-start rounded-md bg-primary px-md py-sm text-label-large font-medium text-on-primary"
        >
          再試行
        </button>
      </div>
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
      <div>
        <p className="text-body-medium text-on-surface">
          AI
          採点は外部のサービスに問い合わせます。その利用料は、ここに入れたキーの持ち主に請求されます。
        </p>
        <p className="mt-xs text-body-medium text-on-surface-variant">
          キーはこの PC の資格情報ストアに保存し、画面には二度と表示しません。
        </p>
      </div>

      {settings.store_unavailable_reason ? (
        <div
          data-testid="settings-api-key-store-unavailable"
          className="rounded-md border border-error bg-error-container p-md text-on-error-container"
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
        <div
          data-testid="settings-api-key-error"
          className="rounded-md border border-error bg-error-container p-md text-on-error-container"
        >
          <p className="text-body-medium">{error}</p>
        </div>
      ) : null}

      {settings.restart_required ? (
        <div className="rounded-md border border-outline-variant bg-surface-container p-md">
          <p
            data-testid="settings-api-key-restart-required"
            className="text-body-medium text-on-surface"
          >
            保存した内容は、まだ採点には使われていません。反映するにはサイドカーを再起動します。
          </p>
          {restartError ? (
            <p className="mt-xs text-body-small text-error">{restartError}</p>
          ) : null}
          {typeof window.autoScoring?.restartSidecar === "function" ? (
            <div className="mt-sm">
              <button
                type="button"
                data-testid="settings-api-key-restart"
                onClick={onRestart}
                disabled={restarting}
                className="rounded-md bg-primary px-md py-sm text-label-large font-medium text-on-primary disabled:opacity-50"
              >
                {restarting ? "再起動中…" : "いま再起動して反映する"}
              </button>
            </div>
          ) : (
            <p className="mt-xs text-body-small text-on-surface-variant">
              この起動方法では画面から再起動できません。アプリを起動し直してください。
            </p>
          )}
        </div>
      ) : null}

      <div
        data-testid="settings-monthly-ai-usage"
        className="rounded-md border border-outline-variant bg-surface-container p-md"
      >
        <h2 className="text-title-medium font-medium text-on-surface">
          今月の AI 採点（このアプリの積算）
        </h2>
        {monthlyDisplay != null ? (
          <div className="mt-xs flex flex-col gap-xs">
            <p
              data-testid="settings-monthly-ai-usage-tokens"
              className="text-body-medium text-on-surface"
            >
              {monthlyDisplay.tokenLine}
            </p>
            {monthlyDisplay.costLine != null ? (
              <p
                data-testid="settings-monthly-ai-usage-cost"
                className="text-body-medium text-on-surface"
              >
                {monthlyDisplay.costLine}
              </p>
            ) : null}
          </div>
        ) : (
          <p className="mt-xs text-body-small text-on-surface-variant">
            読み込み中…
          </p>
        )}
        <div className="mt-md">
          <label
            htmlFor="grading-token-unit-cost"
            className="block text-label-large font-medium text-on-surface"
          >
            採点 1000 トークンあたりの単価
          </label>
          <input
            id="grading-token-unit-cost"
            data-testid="settings-grading-unit-cost"
            type="text"
            inputMode="decimal"
            value={gradingUnitCostInput}
            onChange={(event) => setGradingUnitCostInput(event.target.value)}
            className="mt-xs w-full max-w-xs rounded-md border border-outline bg-surface px-md py-sm text-body-medium text-on-surface"
          />
          <p className="mt-xs text-body-small text-on-surface-variant">
            空欄のままなら金額は出さず、トークン数だけ表示します。
          </p>
          <button
            type="button"
            data-testid="settings-grading-unit-cost-save"
            disabled={gradingCostBusy}
            onClick={() => void onSaveGradingUnitCost()}
            className="mt-sm rounded-md bg-primary px-md py-sm text-label-large font-medium text-on-primary disabled:opacity-50"
          >
            単価を保存
          </button>
        </div>
      </div>

      {/* Transport order card */}
      <div className="rounded-md border border-outline-variant bg-surface-container p-md">
        <h2 className="text-title-medium font-medium text-on-surface">
          使う順番
        </h2>
        <p
          data-testid="settings-api-key-transport-order"
          className="mt-xs text-body-medium text-on-surface"
        >
          {settings.transport_order.length > 0
            ? settings.transport_order
            : "（まだありません）"}
        </p>
        <p className="mt-xs text-body-small text-on-surface-variant">
          {settings.transport_source === "environment"
            ? "この PC の環境変数 AUTO_SCORING_AI_GRADING_TRANSPORT で決まっています。ここでキーを足しても、この順番は変わりません。"
            : settings.transport_source === "builtin_default"
              ? "保存されているキーから決めています。"
              : "キーも環境変数もまだありません。"}
        </p>
      </div>

      {/* Slots */}
      <div className="flex flex-col gap-md">
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
            <div
              key={slot.id}
              className="rounded-md border border-outline-variant bg-surface-container p-md"
            >
              <h3 className="text-title-medium font-medium text-on-surface">
                {slot.label}
              </h3>
              <p
                data-testid={`settings-api-key-status-${slot.id}`}
                className="mt-xs text-body-medium text-on-surface-variant"
              >
                {statusText}
              </p>
              <p className="mt-xs text-body-small text-on-surface-variant">
                {`モデル: ${slot.model}${
                  slot.model_source === "environment"
                    ? "（環境変数）"
                    : "（既定）"
                }`}
              </p>
              <p className="mt-xs select-text text-body-small text-on-surface-variant">
                {`キーの発行: ${slot.console_url}`}
              </p>

              <div className="mt-md">
                <label
                  htmlFor={`api-key-${slot.id}`}
                  className="block text-label-large font-medium text-on-surface"
                >
                  {slot.configured ? "新しいキーに置き換える" : "API キー"}
                </label>
                <input
                  id={`api-key-${slot.id}`}
                  data-testid={`settings-api-key-field-${slot.id}`}
                  type="password"
                  autoComplete="off"
                  value={inputs[slot.id] ?? ""}
                  onChange={(e) => onInputChange(slot.id, e.target.value)}
                  className="mt-xs w-full rounded-md border border-outline bg-surface px-md py-sm text-body-medium text-on-surface"
                />
                {canSave ? (
                  <p className="mt-xs text-body-small text-on-surface-variant">
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
                  className="rounded-md bg-primary px-md py-sm text-label-large font-medium text-on-primary disabled:opacity-50"
                >
                  保存する
                </button>
                <button
                  type="button"
                  data-testid={`settings-api-key-verify-${slot.id}`}
                  onClick={() => void onVerify(slot.id)}
                  disabled={verifyReqs.length > 0}
                  className="rounded-md border border-outline px-md py-sm text-label-large font-medium text-on-surface disabled:opacity-50"
                >
                  疎通を確認する
                </button>
                {slot.configured && slot.key_source === "credential_store" ? (
                  <button
                    type="button"
                    data-testid={`settings-api-key-delete-${slot.id}`}
                    onClick={() => void onDelete(slot.id)}
                    disabled={busySlotId !== null}
                    className="rounded-md px-md py-sm text-label-large font-medium text-error disabled:opacity-50"
                  >
                    保存したキーを削除する
                  </button>
                ) : null}
              </div>

              <DisabledActionReason requirements={saveReqs} />
              <DisabledActionReason requirements={verifyReqs} />

              {verification ? (
                <div className="mt-md flex flex-col gap-xs rounded-md bg-surface p-sm">
                  <div className="flex items-start gap-sm">
                    <span
                      className={`inline-block h-2 w-2 rounded-full mt-sm ${
                        verification.result === "ok" ? "bg-primary" : "bg-error"
                      }`}
                    />
                    <p
                      data-testid={`settings-api-key-verification-${slot.id}`}
                      className={`text-body-medium ${
                        verification.result === "ok"
                          ? "text-primary"
                          : "text-error"
                      }`}
                    >
                      {verification.detail}
                    </p>
                  </div>
                  {formatProviderAccountBalance(
                    verification.provider_account_usage,
                    verification.provider_account_limit,
                  ) != null ? (
                    <p
                      data-testid={`settings-api-key-provider-balance-${slot.id}`}
                      className="text-body-small text-on-surface-variant"
                    >
                      {formatProviderAccountBalance(
                        verification.provider_account_usage,
                        verification.provider_account_limit,
                      )}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
