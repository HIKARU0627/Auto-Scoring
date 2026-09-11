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

const ALL_ROLES: readonly MaterialRole[] = [
  "student_answer",
  "grading_criteria",
  "annotation_resource",
  "annotation_sample",
  "reference",
  "ignore",
];

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
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-body-medium text-on-surface-variant">読み込み中…</p>
      </div>
    );
  }

  if (templates.length === 0) {
    return (
      <div className="flex flex-col gap-md">
        <p className="text-body-medium text-on-surface-variant">
          取込の型がありません。
        </p>
        <button
          type="button"
          data-testid="settings-add-template"
          onClick={addTemplate}
          className="self-start rounded-md bg-primary px-md py-sm text-label-large font-medium text-on-primary"
        >
          型を追加
        </button>
      </div>
    );
  }

  const currentTemplate = templates[selected] ?? templates[0]!;
  const savingReqs = whileRunningRequirements({ running: saving });

  return (
    <div className="flex flex-col gap-lg">
      {/* Template picker and Add button */}
      <div className="flex items-center gap-md">
        <div className="flex-1">
          <label
            htmlFor="template-picker"
            className="block text-label-large font-medium text-on-surface"
          >
            編集する型
          </label>
          <select
            id="template-picker"
            data-testid="settings-template-picker"
            value={selected}
            onChange={(e) => setSelected(Number(e.target.value))}
            className="mt-xs w-full rounded-md border border-outline bg-surface px-md py-sm text-body-medium text-on-surface"
          >
            {templates.map((template, index) => (
              <option key={template.id} value={index}>
                {template.name}
              </option>
            ))}
          </select>
        </div>
        <div className="self-end">
          <button
            type="button"
            data-testid="settings-add-template"
            onClick={addTemplate}
            disabled={saving}
            className="rounded-md border border-outline px-md py-sm text-label-large font-medium text-on-surface disabled:opacity-50"
          >
            型を追加
          </button>
        </div>
      </div>

      {/* Template Name */}
      <div>
        <label
          htmlFor={`template-name-${currentTemplate.id}`}
          className="block text-label-large font-medium text-on-surface"
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
          className="mt-xs w-full rounded-md border border-outline bg-surface px-md py-sm text-body-medium text-on-surface"
        />
      </div>

      {/* Split child directories */}
      <div className="flex items-start gap-sm">
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
          className="mt-xs h-4 w-4 rounded-sm border-outline"
        />
        <label htmlFor="split-child-dirs" className="flex flex-col">
          <span className="text-body-medium font-medium text-on-surface">
            選んだフォルダの直下の各フォルダを、それぞれ別のテストとして取り込む
          </span>
          <span className="text-body-small text-on-surface-variant">
            教科ごとにフォルダが分かれている資料はこれを有効にします。
          </span>
        </label>
      </div>

      {/* Rules list */}
      <div className="flex flex-col gap-sm">
        <h2 className="text-title-medium font-medium text-on-surface">
          規則（上から順に当てはめます）
        </h2>
        <div className="flex flex-col gap-sm">
          {currentTemplate.rules.map((rule, index) => (
            <div
              key={`rule-${index}`}
              className="flex flex-wrap items-center gap-sm rounded-md border border-outline-variant bg-surface-container p-sm"
            >
              {/* Move up/down buttons */}
              <div className="flex flex-col gap-xs">
                <button
                  type="button"
                  title="上へ"
                  disabled={index === 0}
                  onClick={() => moveRule(index, index - 1)}
                  className="text-label-small text-on-surface-variant disabled:opacity-25"
                >
                  ▲
                </button>
                <button
                  type="button"
                  title="下へ"
                  disabled={index === currentTemplate.rules.length - 1}
                  onClick={() => moveRule(index, index + 1)}
                  className="text-label-small text-on-surface-variant disabled:opacity-25"
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
                className="rounded-sm border border-outline bg-surface px-sm py-xs text-body-medium text-on-surface"
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
                className="min-w-30 flex-1 rounded-sm border border-outline bg-surface px-sm py-xs text-body-medium text-on-surface"
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
                className="rounded-sm border border-outline bg-surface px-sm py-xs text-body-medium text-on-surface"
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
                className="rounded-sm border border-outline bg-surface px-sm py-xs text-body-medium text-on-surface"
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
                className="rounded-sm px-sm py-xs text-label-medium text-error hover:bg-error-container/20"
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
          className="self-start rounded-md border border-outline px-md py-sm text-label-large font-medium text-on-surface"
        >
          規則を追加
        </button>
      </div>

      <hr className="border-outline-variant" />

      {/* Unit Cost */}
      <div>
        <label
          htmlFor="unit-cost"
          className="block text-label-large font-medium text-on-surface"
        >
          AI判定 1件あたりの単価
        </label>
        <input
          id="unit-cost"
          data-testid="settings-unit-cost"
          type="text"
          value={costText}
          onChange={(e) => setCostText(e.target.value)}
          className="mt-xs w-full rounded-md border border-outline bg-surface px-md py-sm text-body-medium text-on-surface"
        />
        <p className="mt-xs text-body-small text-on-surface-variant">
          このアプリは提供元の料金を知りません。空欄のままなら、取込画面では「単価が未設定」と表示します。
        </p>
      </div>

      {error ? (
        <div className="rounded-md border border-error bg-error-container p-md text-on-error-container">
          <p className="text-body-medium">{error}</p>
        </div>
      ) : null}

      {savedNotice ? (
        <p
          data-testid="settings-saved-notice"
          className="text-body-medium text-primary"
        >
          {savedNotice}
        </p>
      ) : null}

      <div>
        <button
          type="button"
          data-testid="settings-save"
          onClick={() => void onSave()}
          disabled={savingReqs.length > 0}
          className="rounded-md bg-primary px-md py-sm text-label-large font-medium text-on-primary disabled:opacity-50"
        >
          保存する
        </button>
        <DisabledActionReason requirements={savingReqs} />
      </div>
    </div>
  );
}
