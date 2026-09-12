import {
  useCallback,
  useEffect,
  useState,
  type DragEvent,
  type JSX,
} from "react";
import { ArrowDown, ArrowUp, GripVertical } from "lucide-react";

import {
  clearTransportOrder,
  deleteApiKey,
  loadApiKeySettings,
  saveProviderSettings,
  saveTransportOrder,
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
  TRANSPORT_ORDER_HANDLE_CLASS,
  transportOrderItemClass,
} from "./settings-presentation.js";

function errorText(error: unknown): string {
  return error instanceof SettingsDataError
    ? error.message
    : error instanceof Error
      ? error.message
      : String(error);
}

/** Input key for one editable setting of one provider slot. */
function settingKey(slotId: string, variable: string): string {
  return `${slotId}::${variable}`;
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
  const [busyOrder, setBusyOrder] = useState<boolean>(false);
  const [verified, setVerified] = useState<
    Record<string, VerifyApiKeyResponse>
  >({});
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [settingInputs, setSettingInputs] = useState<Record<string, string>>(
    {},
  );
  const [order, setOrder] = useState<string[]>([]);
  const [draggingTransport, setDraggingTransport] = useState<string | null>(
    null,
  );
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [restarting, setRestarting] = useState<boolean>(false);
  const [restartError, setRestartError] = useState<string | null>(null);
  const [monthlyUsage, setMonthlyUsage] = useState<AiUsageNumbers | null>(null);
  const [gradingUnitCostInput, setGradingUnitCostInput] = useState<string>("");
  const [gradingCostBusy, setGradingCostBusy] = useState<boolean>(false);

  const absorb = useCallback((data: ApiKeySettingsResponse) => {
    setSettings(data);
    const next: Record<string, string> = {};
    for (const slot of data.keys) {
      next[settingKey(slot.id, slot.model_variable)] = slot.model;
      for (const item of slot.text_settings) {
        next[settingKey(slot.id, item.variable)] = item.value;
      }
    }
    setSettingInputs(next);
    setKeyInputs({});
    const configuredOrder = data.transport_order
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
    setOrder(
      configuredOrder.length > 0
        ? configuredOrder
        : [...data.available_transports],
    );
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, monthly, unitCost] = await Promise.all([
        loadApiKeySettings(client),
        loadMonthlyAiUsage(client).catch(() => null),
        loadGradingTokenUnitCost(client).catch(() => null),
      ]);
      absorb(data);
      setMonthlyUsage(monthly);
      setGradingUnitCostInput(unitCost == null ? "" : String(unitCost));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [client, absorb]);

  useEffect(() => {
    void load();
  }, [load]);

  const onKeyInputChange = (slotId: string, value: string) => {
    setKeyInputs((prev) => ({ ...prev, [slotId]: value }));
  };

  const onSettingInputChange = (
    slotId: string,
    variable: string,
    value: string,
  ) => {
    setSettingInputs((prev) => ({
      ...prev,
      [settingKey(slotId, variable)]: value,
    }));
  };

  const onSave = async (slot: ApiKeyStatusModel) => {
    const keyValue = (keyInputs[slot.id] ?? "").trim();
    // Only send what actually changed, so saving a slot does not copy the
    // built-in defaults into the credential store as if the user chose them.
    const values: Record<string, string | null> = {};
    const modelValue =
      settingInputs[settingKey(slot.id, slot.model_variable)] ?? slot.model;
    if (modelValue !== slot.model) {
      values[slot.model_variable] = modelValue;
    }
    for (const item of slot.text_settings) {
      const current =
        settingInputs[settingKey(slot.id, item.variable)] ?? item.value;
      if (current !== item.value) {
        values[item.variable] = current;
      }
    }
    if (slot.key_variable != null && keyValue.length > 0) {
      values[slot.key_variable] = keyValue;
    }
    if (Object.keys(values).length === 0) {
      setError("変更された設定がありません。");
      return;
    }
    // Clear the key field immediately so it never sits in the input.
    setKeyInputs((prev) => ({ ...prev, [slot.id]: "" }));
    setVerified((prev) => {
      const next = { ...prev };
      delete next[slot.id];
      return next;
    });
    setBusySlotId(slot.id);
    setError(null);
    try {
      const updated = await saveProviderSettings(client, slot.id, values);
      absorb(updated);
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
      absorb(updated);
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

  const moveTransportTo = (fromIndex: number, toIndex: number) => {
    setOrder((prev) => {
      if (
        fromIndex === toIndex ||
        fromIndex < 0 ||
        toIndex < 0 ||
        fromIndex >= prev.length ||
        toIndex >= prev.length
      ) {
        return prev;
      }
      const next = [...prev];
      const [moved] = next.splice(fromIndex, 1);
      if (moved === undefined) {
        return prev;
      }
      next.splice(toIndex, 0, moved);
      return next;
    });
  };

  const moveTransport = (index: number, delta: number) => {
    moveTransportTo(index, index + delta);
  };

  // Issue #448: drag-and-drop is the pointer path to the same reorder the
  // 「上へ」「下へ」 buttons already give the keyboard. The row being dragged
  // keeps its state here rather than in `dataTransfer`, because `dataTransfer`
  // is unreadable during `dragover` in every browser that matters and the drop
  // target has to know what is in flight.
  const onOrderDragStart = (
    event: DragEvent<HTMLSpanElement>,
    transport: string,
  ) => {
    setDraggingTransport(transport);
    setDragOverIndex(order.indexOf(transport));
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", transport);
    }
  };

  const onOrderDragOver = (event: DragEvent<HTMLLIElement>, index: number) => {
    if (draggingTransport === null) {
      return;
    }
    // Without this the row is not a drop target at all and the browser shows
    // the "no-drop" cursor.
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "move";
    }
    setDragOverIndex(index);
  };

  const onOrderDrop = (event: DragEvent<HTMLLIElement>, index: number) => {
    event.preventDefault();
    if (draggingTransport !== null) {
      moveTransportTo(order.indexOf(draggingTransport), index);
    }
    onOrderDragEnd();
  };

  const onOrderDragEnd = () => {
    setDraggingTransport(null);
    setDragOverIndex(null);
  };

  const onSaveOrder = async () => {
    setBusyOrder(true);
    setError(null);
    try {
      const updated = await saveTransportOrder(client, order);
      absorb(updated);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusyOrder(false);
    }
  };

  const onRevertOrder = async () => {
    setBusyOrder(true);
    setError(null);
    try {
      const updated = await clearTransportOrder(client);
      absorb(updated);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusyOrder(false);
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
  const labelByTransport = new Map(
    settings.keys.map((slot) => [slot.transport, slot.label]),
  );

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

  const orderDescription =
    settings.transport_source === "credential_store"
      ? "画面で保存した順番が使われています。上で並べ替えて保存できます。"
      : settings.transport_source === "environment"
        ? "この PC の環境変数 AUTO_SCORING_AI_GRADING_TRANSPORT で決まっています。上で並べ替えて保存すると、保存した順番が優先されます。"
        : settings.transport_source === "builtin_default"
          ? "保存されているキーから自動で決めています。上で並べ替えて保存できます。"
          : "キーも環境変数もまだありません。上で並べ替えて保存すると、その順番で使われます。";

  return (
    <div className="flex flex-col gap-lg">
      <section className={SETTINGS_CARD_CLASS}>
        <h2 className={SETTINGS_CARD_HEADING_CLASS}>AI 採点に使うキー</h2>
        <p className="mt-xs text-body-medium text-on-surface-variant">
          AI
          採点は外部のサービスに問い合わせます。その利用料は、ここに入れたキーの持ち主に請求されます。
        </p>
        <p className="mt-xs text-body-medium text-on-surface-variant">
          キーはこの PC
          の資格情報ストアに保存し、画面には二度と表示しません。モデルや Vertex
          AI のプロジェクトなど、秘密でない設定は表示されます。
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
                // A keyless provider's "credential" is the host, and the
                // verify button is exactly how the user checks it -- it must
                // not be disabled for a missing key there is none of.
                configured: slot.key_variable == null ? true : slot.configured,
              });
              const verification = verified[slot.id];
              // Issue #448: the suggestions are a convenience, not a catalog.
              // The effective model is folded in so the box the user sees is
              // also the one the list can complete back to.
              const modelOptions = Array.from(
                new Set(
                  [slot.model, ...slot.suggested_models].filter(
                    (option) => option.length > 0,
                  ),
                ),
              );

              const statusText =
                slot.key_variable == null
                  ? slot.auth_note
                  : slot.configured
                    ? slot.key_source === "credential_store"
                      ? "保存済み（この PC の資格情報ストア）"
                      : `環境変数 ${slot.key_variable} から読み込み済み`
                    : "未設定";

              const hostText =
                slot.host_available === true
                  ? "この PC で利用できます。"
                  : slot.host_available === false
                    ? "この PC では利用できません。"
                    : "「疎通を確認する」でこの PC での利用可否を確認できます。";

              return (
                <section key={slot.id} className={SETTINGS_CARD_CLASS}>
                  <div className="flex flex-wrap items-center justify-between gap-sm">
                    <h3 className={SETTINGS_ITEM_HEADING_CLASS}>
                      {slot.label}
                    </h3>
                    <span
                      className={apiKeyStatePillClass(
                        slot.key_variable == null
                          ? slot.host_available === true
                          : slot.configured,
                      )}
                    >
                      <span aria-hidden>
                        {slot.key_variable == null
                          ? slot.host_available === true
                            ? "✓"
                            : "−"
                          : slot.configured
                            ? "✓"
                            : "−"}
                      </span>
                      {slot.key_variable == null
                        ? slot.host_available === true
                          ? "利用可"
                          : slot.host_available === false
                            ? "利用不可"
                            : "未確認"
                        : slot.configured
                          ? "設定済み"
                          : "未設定"}
                    </span>
                  </div>
                  <p
                    data-testid={`settings-api-key-status-${slot.id}`}
                    className="mt-xs text-body-medium text-on-surface-variant"
                  >
                    {statusText}
                  </p>
                  {slot.key_variable == null ? (
                    <p
                      data-testid={`settings-api-key-host-${slot.id}`}
                      className="mt-xs text-xs text-on-surface-variant"
                    >
                      {hostText}
                    </p>
                  ) : null}
                  {slot.console_url.length > 0 ? (
                    <p className="mt-xs select-text text-xs text-on-surface-variant">
                      {`キーの発行: ${slot.console_url}`}
                    </p>
                  ) : null}

                  <div className="mt-md">
                    <label
                      htmlFor={`api-key-model-${slot.id}`}
                      className={SETTINGS_LABEL_CLASS}
                    >
                      モデル
                    </label>
                    <input
                      id={`api-key-model-${slot.id}`}
                      data-testid={`settings-api-key-model-${slot.id}`}
                      type="text"
                      list={`api-key-model-options-${slot.id}`}
                      value={
                        settingInputs[
                          settingKey(slot.id, slot.model_variable)
                        ] ?? slot.model
                      }
                      placeholder={slot.model}
                      onChange={(event) =>
                        onSettingInputChange(
                          slot.id,
                          slot.model_variable,
                          event.target.value,
                        )
                      }
                      className={SETTINGS_INPUT_CLASS}
                    />
                    <datalist
                      id={`api-key-model-options-${slot.id}`}
                      data-testid={`settings-api-key-model-options-${slot.id}`}
                    >
                      {modelOptions.map((option) => (
                        <option key={option} value={option} />
                      ))}
                    </datalist>
                    <p className="mt-xs text-xs text-on-surface-variant">
                      {slot.model_source === "environment"
                        ? "環境変数で設定されています。"
                        : slot.model_source === "credential_store"
                          ? "画面で保存した値です。"
                          : "既定のモデルを使います。"}
                      {" 候補から選ぶことも、直接入力することもできます。"}
                    </p>
                  </div>

                  {slot.text_settings.map((item) => (
                    <div key={item.variable} className="mt-md">
                      <label
                        htmlFor={`api-key-setting-${slot.id}-${item.variable}`}
                        className={SETTINGS_LABEL_CLASS}
                      >
                        {item.label}
                      </label>
                      <input
                        id={`api-key-setting-${slot.id}-${item.variable}`}
                        data-testid={`settings-api-key-setting-${slot.id}-${item.variable}`}
                        type="text"
                        value={
                          settingInputs[settingKey(slot.id, item.variable)] ??
                          item.value
                        }
                        placeholder={
                          item.placeholder.length > 0
                            ? item.placeholder
                            : item.default_value
                        }
                        onChange={(event) =>
                          onSettingInputChange(
                            slot.id,
                            item.variable,
                            event.target.value,
                          )
                        }
                        className={SETTINGS_INPUT_CLASS}
                      />
                      {item.help_text.length > 0 ? (
                        <p className="mt-xs text-xs text-on-surface-variant">
                          {item.help_text}
                        </p>
                      ) : null}
                    </div>
                  ))}

                  {slot.key_variable != null ? (
                    <div className="mt-md">
                      <label
                        htmlFor={`api-key-${slot.id}`}
                        className={SETTINGS_LABEL_CLASS}
                      >
                        {slot.configured
                          ? "新しいキーに置き換える"
                          : "API キー"}
                      </label>
                      <input
                        id={`api-key-${slot.id}`}
                        data-testid={`settings-api-key-field-${slot.id}`}
                        type="password"
                        autoComplete="new-password"
                        placeholder="•••• •••• ••••"
                        value={keyInputs[slot.id] ?? ""}
                        onChange={(e) =>
                          onKeyInputChange(slot.id, e.target.value)
                        }
                        className={SETTINGS_INPUT_CLASS}
                      />
                      {canSave ? (
                        <p className="mt-xs text-xs text-on-surface-variant">
                          保存すると、この欄は空になります。保存したキーは表示できません。
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="mt-md flex flex-wrap items-center gap-sm">
                    <button
                      type="button"
                      data-testid={`settings-api-key-save-${slot.id}`}
                      onClick={() => void onSave(slot)}
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
                    {slot.key_variable != null &&
                    slot.configured &&
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
              {order.length > 0 ? order.join(" → ") : "（まだありません）"}
            </p>
            {/* The numbered rows below already spell the order out, but a
                reorder triggered by a drag announces nothing to a screen
                reader, so the change is voiced here. */}
            <p
              role="status"
              data-testid="settings-transport-order-announcement"
              className="sr-only"
            >
              {order.length > 0
                ? `現在の順番: ${order
                    .map(
                      (transport, index) =>
                        `${index + 1}. ${
                          labelByTransport.get(transport) ?? transport
                        }`,
                    )
                    .join("、")}`
                : "使う順番はまだありません。"}
            </p>
            <p className="mt-xs text-xs text-on-surface-variant">
              つまみをドラッグするか、「上へ」「下へ」で並べ替えられます。
            </p>
            <ul className="mt-sm flex flex-col gap-xs">
              {order.map((transport, index) => (
                <li
                  key={transport}
                  data-testid={`settings-transport-order-item-${transport}`}
                  data-dragging={
                    draggingTransport === transport ? "true" : undefined
                  }
                  data-drop-target={
                    draggingTransport !== null &&
                    draggingTransport !== transport &&
                    dragOverIndex === index
                      ? "true"
                      : undefined
                  }
                  onDragOver={(event) => onOrderDragOver(event, index)}
                  onDrop={(event) => onOrderDrop(event, index)}
                  className={transportOrderItemClass({
                    dragging: draggingTransport === transport,
                    dropTarget:
                      draggingTransport !== null &&
                      draggingTransport !== transport &&
                      dragOverIndex === index,
                  })}
                >
                  <span
                    draggable={!busyOrder}
                    aria-hidden
                    data-testid={`settings-transport-order-handle-${transport}`}
                    onDragStart={(event) => onOrderDragStart(event, transport)}
                    onDragEnd={onOrderDragEnd}
                    className={TRANSPORT_ORDER_HANDLE_CLASS}
                  >
                    <GripVertical className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1 truncate">
                    {index + 1}. {labelByTransport.get(transport) ?? transport}
                  </span>
                  <button
                    type="button"
                    data-testid={`settings-transport-order-up-${transport}`}
                    aria-label={`${labelByTransport.get(transport) ?? transport} を上へ`}
                    onClick={() => moveTransport(index, -1)}
                    disabled={index === 0 || busyOrder}
                    className={SETTINGS_BUTTON_SECONDARY_CLASS}
                  >
                    <ArrowUp aria-hidden className="size-4" />
                  </button>
                  <button
                    type="button"
                    data-testid={`settings-transport-order-down-${transport}`}
                    aria-label={`${labelByTransport.get(transport) ?? transport} を下へ`}
                    onClick={() => moveTransport(index, 1)}
                    disabled={index === order.length - 1 || busyOrder}
                    className={SETTINGS_BUTTON_SECONDARY_CLASS}
                  >
                    <ArrowDown aria-hidden className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-xs text-xs text-on-surface-variant">
              {orderDescription}
            </p>
            <div className="mt-sm flex flex-wrap items-center gap-sm">
              <button
                type="button"
                data-testid="settings-transport-order-save"
                onClick={() => void onSaveOrder()}
                disabled={busyOrder}
                className={SETTINGS_BUTTON_PRIMARY_CLASS}
              >
                {busyOrder ? "処理中…" : "この順番で保存"}
              </button>
              {settings.transport_order_stored ? (
                <button
                  type="button"
                  data-testid="settings-transport-order-revert"
                  onClick={() => void onRevertOrder()}
                  disabled={busyOrder}
                  className={SETTINGS_BUTTON_SECONDARY_CLASS}
                >
                  保存した順番を削除（環境変数に戻す）
                </button>
              ) : null}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
