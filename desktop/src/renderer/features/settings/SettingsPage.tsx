import { useState, type JSX } from "react";

import { ShellScreen } from "../../navigation/ShellScreen.js";
import { ApiKeyTab } from "./ApiKeyTab.js";
import { IntakeTemplateTab } from "./IntakeTemplateTab.js";

type TabKey = "intake" | "api-key";

export function SettingsPage(): JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>("intake");

  return (
    <ShellScreen title="設定">
      <div className="mb-lg flex border-b border-outline-variant">
        <button
          type="button"
          data-testid="settings-tab-intake"
          onClick={() => setActiveTab("intake")}
          className={`border-b-2 px-lg py-sm text-title-medium font-medium transition-colors ${
            activeTab === "intake"
              ? "border-primary text-primary"
              : "border-transparent text-on-surface-variant hover:text-on-surface"
          }`}
        >
          取込の型
        </button>
        <button
          type="button"
          data-testid="settings-tab-api-key"
          onClick={() => setActiveTab("api-key")}
          className={`border-b-2 px-lg py-sm text-title-medium font-medium transition-colors ${
            activeTab === "api-key"
              ? "border-primary text-primary"
              : "border-transparent text-on-surface-variant hover:text-on-surface"
          }`}
        >
          API キー
        </button>
      </div>

      {activeTab === "intake" ? <IntakeTemplateTab /> : <ApiKeyTab />}
    </ShellScreen>
  );
}
