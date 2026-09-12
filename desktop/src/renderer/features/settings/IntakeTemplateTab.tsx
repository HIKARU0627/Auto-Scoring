import { useCallback, useEffect, useState, type JSX } from "react";

import {
  loadIntakeCost,
  loadIntakeTemplates,
  saveIntakeCost,
  saveIntakeTemplates,
  SettingsDataError,
  type IntakeRuleModel,
  type IntakeTemplateModel,
  type MaterialRole,
  type Requirement,
  type RuleScope,
} from "../../api/settings-data.js";
import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import { whileRunningRequirements } from "../../core/action-requirements.js";
import { materialRoleLabel } from "../../core/material-role-labels.js";
import { DisabledActionReason } from "../intake/DisabledActionReason.js";
import {
  SETTINGS_BUTTON_PRIMARY_CLASS,
  SETTINGS_BUTTON_SECONDARY_CLASS,
  SETTINGS_CARD_CLASS,
  SETTINGS_CARD_HEADING_CLASS,
  SETTINGS_ICON_TILE_CLASS,
  SETTINGS_INPUT_CLASS,
  SETTINGS_LABEL_CLASS,
  SETTINGS_SELECT_CLASS,
} from "./settings-presentation.js";

const ALL_ROLES: readonly MaterialRole[] = [
  "student_answer",
  "grading_criteria",
  "annotation_resource",
  "annotation_sample",
  "reference",
  "ignore",
];

const RULE_SELECT_CLASS =
  "rounded-sm bg-surface-container-high px-sm py-xs text-body-medium text-on-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary";

function IntakeLoading(): JSX.Element {
  return (
    <div
      data-testid="settings-intake-loading"
      aria-busy="true"
      aria-live="polite"
      className="flex flex-col gap-lg"
    >
      <span className="sr-only">取込の型を読み込んでいます…</span>
      <div className={`${SETTINGS_CARD_CLASS} animate-pulse`}>
        <div className="h-5 w-40 rounded-md bg-surface-container-high" />
        <div className="mt-md h-10 w-full rounded-md bg-surface-container-high" />
        <div className="mt-lg h-24 w-full rounded-md bg-surface-container-high" />
      </div>
      <div className={`${SETTINGS_CARD_CLASS} animate-pulse`}>
        <div className="h-5 w-32 rounded-md bg-surface-container-high" />
        <div className="mt-md h-10 w-full rounded-md bg-surface-container-high" />
      </div>
    </div>
  );
}

export function IntakeTemplateTab(): JSX.Element {
  const client = useSidecarClient();

  const [templates, setTemplates] = useState<IntakeTemplateModel[]>([]);
  const [selected, setSelected] = useState<number>(0);
  const [costText, setCostText] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [loadedTemplates, loadedCost] = await Promise.all([
        loadIntakeTemplates(client),
        loadIntakeCost(client),
      ]);
      setTemplates(loadedTemplates);
      setSelected((prev) =>
        loadedTemplates.length === 0
          ? 0
          : Math.min(Math.max(0, prev), loadedTemplates.length - 1),
      );
      setCostText(loadedCost !== null ? String(loadedCost) : "");
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

  const updateTemplate = (
    updater: (current: IntakeTemplateModel) => IntakeTemplateModel,
  ) => {
    setTemplates((prev) =>
      prev.map((t, i) => (i === selected ? updater(t) : t)),
    );
  };

  const addTemplate = () => {
    const newTemplate: IntakeTemplateModel = {
      id: `template-${Date.now()}`,
      name: "新しい型",
      split_child_directories: true,
      rules: [],
    };
    setTemplates((prev) => [...prev, newTemplate]);
    setSelected(templates.length);
  };

  const addRule = () => {
    const newRule: IntakeRuleModel = {
      scope: "file",
      pattern: "*",
      role: "reference",
      requirement: "optional",
    };
    updateTemplate((current) => ({
      ...current,
      rules: [...current.rules, newRule],
    }));
  };

  const removeRule = (ruleIndex: number) => {
    updateTemplate((current) => ({
      ...current,
      rules: current.rules.filter((_, i) => i !== ruleIndex),
    }));
  };

  const updateRule = (ruleIndex: number, updated: IntakeRuleModel) => {
    updateTemplate((current) => ({
      ...current,
      rules: current.rules.map((r, i) => (i === ruleIndex ? updated : r)),
    }));
  };

  const moveRule = (fromIndex: number, toIndex: number) => {
    updateTemplate((current) => {
      const nextRules = [...current.rules];
      const [moved] = nextRules.splice(fromIndex, 1);
      if (moved !== undefined) {
        nextRules.splice(toIndex, 0, moved);
      }
      return { ...current, rules: nextRules };
    });
  };

  const onSave = async () => {
    setSaving(true);
    setError(null);
    setSavedNotice(null);
    try {
      const rawCost = costText.trim();
      let parsedCost: number | null = null;
      if (rawCost.length > 0) {
        parsedCost = Number(rawCost);
        if (Number.isNaN(parsedCost)) {
          setError("1件あたりの単価は数字で入力してください。");
          setSaving(false);
          return;
        }
      }

      const [savedTemplates] = await Promise.all([
        saveIntakeTemplates(client, templates),
        saveIntakeCost(client, parsedCost),
      ]);
      setTemplates(savedTemplates);
      setSavedNotice("保存しました。次の取込から反映されます。");
    } catch (err) {
      setError(
        err instanceof SettingsDataError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <IntakeLoading />;
  }

  if (templates.length === 0) {
    return (
      <section className={SETTINGS_CARD_CLASS}>
        <div className="flex items-start gap-md">
          <span aria-hidden className={SETTINGS_ICON_TILE_CLASS}>
            +
          </span>
          <div className="min-w-0 flex-1">
            <h2 className={SETTINGS_CARD_HEADING_CLASS}>取込の型</h2>
            <p
              data-testid="settings-intake-empty"
              className="mt-xs text-body-medium text-on-surface-variant"
            >
              取込の型がありません。型を追加して、ファイル名やフォルダ名から役割を決める規則を作ってください。
            </p>
            <button
              type="button"
              data-testid="settings-add-template"
              onClick={addTemplate}
              className={`${SETTINGS_BUTTON_PRIMARY_CLASS} mt-md`}
            >
              型を追加
            </button>
          </div>
        </div>
      </section>
    );
  }

  const currentTemplate = templates[selected] ?? templates[0]!;
  const savingReqs = whileRunningRequirements({ running: saving });

  return (
    <div className="flex flex-col gap-lg">
      {error ? (
        <div className="rounded-xl bg-error-container px-lg py-md text-on-error-container">
          <p className="text-body-medium">{error}</p>
        </div>
      ) : null}

      {savedNotice ? (
        <p
          data-testid="settings-saved-notice"
          role="status"
          className="rounded-xl bg-success-container px-lg py-md text-body-medium text-on-success-container"
        >
          {savedNotice}
        </p>
      ) : null}

      {/* Template picker and Add button */}
      <section className={SETTINGS_CARD_CLASS}>
        <div className="flex flex-wrap items-end gap-md">
          <div className="min-w-0 flex-1">
            <label htmlFor="template-picker" className={SETTINGS_LABEL_CLASS}>
              編集する型
            </label>
            <select
              id="template-picker"
              data-testid="settings-template-picker"
              value={selected}
              onChange={(e) => setSelected(Number(e.target.value))}
              className={`${SETTINGS_SELECT_CLASS} select-themed`}
            >
              {templates.map((template, index) => (
                <option key={template.id} value={index}>
                  {template.name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            data-testid="settings-add-template"
            onClick={addTemplate}
            disabled={saving}
            className={SETTINGS_BUTTON_SECONDARY_CLASS}
          >
            型を追加
          </button>
        </div>

        {/* Template Name */}
        <div className="mt-lg">
          <label
            htmlFor={`template-name-${currentTemplate.id}`}
            className={SETTINGS_LABEL_CLASS}
          >
            型の名前
          </label>
          <input
            id={`template-name-${currentTemplate.id}`}
            data-testid={`settings-template-name-${currentTemplate.id}`}
            type="text"
            value={currentTemplate.name}
            onChange={(e) =>
              updateTemplate((current) => ({
                ...current,
                name: e.target.value,
              }))
            }
            className={SETTINGS_INPUT_CLASS}
          />
        </div>

        {/* Split child directories */}
        <div className="mt-lg flex items-start gap-sm">
          <input
            id="split-child-dirs"
            data-testid="settings-split-child-directories"
            type="checkbox"
            checked={currentTemplate.split_child_directories ?? true}
            onChange={(e) =>
              updateTemplate((current) => ({
                ...current,
                split_child_directories: e.target.checked,
              }))
            }
            className="mt-xs size-4 shrink-0 rounded-sm border-outline accent-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          />
          <label htmlFor="split-child-dirs" className="flex min-w-0 flex-col">
            <span className="text-body-medium font-medium text-on-surface">
              選んだフォルダの直下の各フォルダを、それぞれ別のテストとして取り込む
            </span>
            <span className="text-xs text-on-surface-variant">
              教科ごとにフォルダが分かれている資料はこれを有効にします。
            </span>
          </label>
        </div>
      </section>

      {/* Rules list */}
      <section className={SETTINGS_CARD_CLASS}>
        <h2 className={SETTINGS_CARD_HEADING_CLASS}>
          規則（上から順に当てはめます）
        </h2>
        <div className="mt-md flex flex-col gap-sm">
          {currentTemplate.rules.map((rule, index) => (
            <div
              key={`rule-${index}`}
              className="flex flex-wrap items-center gap-sm rounded-lg bg-surface-container-high p-sm"
            >
              {/* Move up/down buttons */}
              <div className="flex flex-col gap-xs">
                <button
                  type="button"
                  title="上へ"
                  aria-label="この規則を上へ"
                  disabled={index === 0}
                  onClick={() => moveRule(index, index - 1)}
                  className="rounded-sm text-xs text-on-surface-variant hover:bg-surface-container focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary disabled:opacity-25"
                >
                  ▲
                </button>
                <button
                  type="button"
                  title="下へ"
                  aria-label="この規則を下へ"
                  disabled={index === currentTemplate.rules.length - 1}
                  onClick={() => moveRule(index, index + 1)}
                  className="rounded-sm text-xs text-on-surface-variant hover:bg-surface-container focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary disabled:opacity-25"
                >
                  ▼
                </button>
              </div>

              {/* Scope */}
              <select
                data-testid={`settings-rule-scope-${index}`}
                value={rule.scope}
                onChange={(e) =>
                  updateRule(index, {
                    ...rule,
                    scope: e.target.value as RuleScope,
                  })
                }
                className={`${RULE_SELECT_CLASS} select-themed`}
                aria-label={`規則${index + 1} の対象`}
              >
                <option value="file">ファイル名</option>
                <option value="folder">フォルダ名</option>
              </select>

              {/* Pattern */}
              <input
                data-testid={`settings-rule-pattern-${index}`}
                type="text"
                value={rule.pattern}
                onChange={(e) =>
                  updateRule(index, {
                    ...rule,
                    pattern: e.target.value,
                  })
                }
                className="min-w-30 flex-1 rounded-sm bg-surface-container-high px-sm py-xs text-body-medium text-on-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                aria-label={`規則${index + 1} のパターン`}
              />

              {/* Role */}
              <select
                data-testid={`settings-rule-role-${index}`}
                value={rule.role}
                onChange={(e) =>
                  updateRule(index, {
                    ...rule,
                    role: e.target.value as MaterialRole,
                  })
                }
                className={`${RULE_SELECT_CLASS} select-themed`}
                aria-label={`規則${index + 1} の役割`}
              >
                {ALL_ROLES.map((role) => (
                  <option key={role} value={role}>
                    {materialRoleLabel(role)}
                  </option>
                ))}
              </select>

              {/* Requirement */}
              <select
                data-testid={`settings-rule-requirement-${index}`}
                value={rule.requirement}
                onChange={(e) =>
                  updateRule(index, {
                    ...rule,
                    requirement: e.target.value as Requirement,
                  })
                }
                className={`${RULE_SELECT_CLASS} select-themed`}
                aria-label={`規則${index + 1} の必須度`}
              >
                <option value="required">必須</option>
                <option value="recommended">推奨</option>
                <option value="optional">任意</option>
              </select>

              {/* Remove */}
              <button
                type="button"
                data-testid={`settings-remove-rule-${index}`}
                onClick={() => removeRule(index)}
                className="rounded-sm px-sm py-xs text-xs text-error hover:bg-error-container/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-error"
              >
                削除
              </button>
            </div>
          ))}
        </div>

        <button
          type="button"
          data-testid="settings-add-rule"
          onClick={addRule}
          className={`${SETTINGS_BUTTON_SECONDARY_CLASS} mt-md`}
        >
          規則を追加
        </button>
      </section>

      {/* Unit Cost */}
      <section className={SETTINGS_CARD_CLASS}>
        <label htmlFor="unit-cost" className={SETTINGS_LABEL_CLASS}>
          AI判定 1件あたりの単価
        </label>
        <input
          id="unit-cost"
          data-testid="settings-unit-cost"
          type="text"
          value={costText}
          onChange={(e) => setCostText(e.target.value)}
          className={`${SETTINGS_INPUT_CLASS} max-w-80`}
        />
        <p className="mt-xs text-xs text-on-surface-variant">
          このアプリは提供元の料金を知りません。空欄のままなら、取込画面では「単価が未設定」と表示します。
        </p>
      </section>

      <div>
        <button
          type="button"
          data-testid="settings-save"
          onClick={() => void onSave()}
          disabled={savingReqs.length > 0}
          className={SETTINGS_BUTTON_PRIMARY_CLASS}
        >
          {saving ? "保存中…" : "保存する"}
        </button>
        <DisabledActionReason requirements={savingReqs} />
      </div>
    </div>
  );
}
