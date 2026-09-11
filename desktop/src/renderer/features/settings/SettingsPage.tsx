import { useRef, useState, type JSX, type KeyboardEvent } from "react";

import { ShellScreen } from "../../navigation/ShellScreen.js";
import { ApiKeyTab } from "./ApiKeyTab.js";
import { IntakeTemplateTab } from "./IntakeTemplateTab.js";

type TabKey = "intake" | "api-key";

const TABS: readonly { key: TabKey; testId: string; label: string }[] = [
  { key: "intake", testId: "settings-tab-intake", label: "取込の型" },
  { key: "api-key", testId: "settings-tab-api-key", label: "API キー" },
];

export function SettingsPage(): JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>("intake");
  const tabRefs = useRef(new Map<TabKey, HTMLButtonElement>());

  const onTabKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    key: TabKey,
  ) => {
    const index = TABS.findIndex((tab) => tab.key === key);
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") {
      nextIndex = (index + 1) % TABS.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (index - 1 + TABS.length) % TABS.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = TABS.length - 1;
    }
    if (nextIndex === null) {
      return;
    }
    event.preventDefault();
    const next = TABS[nextIndex];
    if (next === undefined) {
      return;
    }
    setActiveTab(next.key);
    tabRefs.current.get(next.key)?.focus();
  };

  return (
    <ShellScreen title="設定">
      <div
        role="tablist"
        aria-label="設定の種類"
        className="mb-lg inline-flex gap-xs rounded-xl bg-surface-container p-xs"
      >
        {TABS.map((tab) => {
          const selected = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              ref={(node) => {
                if (node === null) {
                  tabRefs.current.delete(tab.key);
                } else {
                  tabRefs.current.set(tab.key, node);
                }
              }}
              type="button"
              role="tab"
              id={`settings-tab-${tab.key}`}
              aria-selected={selected}
              aria-controls="settings-tab-panel"
              tabIndex={selected ? 0 : -1}
              data-testid={tab.testId}
              onClick={() => setActiveTab(tab.key)}
              onKeyDown={(event) => onTabKeyDown(event, tab.key)}
              className={`rounded-lg px-lg py-sm text-ui-label font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${
                selected
                  ? "bg-primary text-on-primary"
                  : "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div
        id="settings-tab-panel"
        role="tabpanel"
        aria-labelledby={`settings-tab-${activeTab}`}
      >
        {activeTab === "intake" ? <IntakeTemplateTab /> : <ApiKeyTab />}
      </div>
    </ShellScreen>
  );
}
