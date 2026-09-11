import type { JSX } from "react";

import {
  type HomeDashboard,
  HOME_TEST_PHASE_ORDER,
  homeTestPhaseMeta,
} from "../../core/home-dashboard.js";
import {
  HomeDonutChart,
  type HomePhaseSlice,
} from "./charts/HomeDonutChart.js";
import { PANEL_TITLE_STYLE } from "./home-format.js";

/**
 * テストの進捗 panel (Issue #336): preparing / in-progress / done over every
 * registered test. A test's phase is derived from a real `TestStatus` plus
 * whether its answers are all human-confirmed, so no slice is invented.
 */
export function HomeTestDonutPanel({
  dashboard,
}: {
  dashboard: HomeDashboard;
}): JSX.Element {
  const total = dashboard.tests.length;
  const slices: HomePhaseSlice[] = HOME_TEST_PHASE_ORDER.map((phase) => {
    const count = dashboard.phaseCount(phase);
    return {
      phase,
      label: homeTestPhaseMeta(phase).label,
      count,
      percent: total > 0 ? Math.round((count / total) * 100) : 0,
    };
  });

  return (
    <section
      data-testid="home-tests-panel"
      className="h-full min-w-0 rounded-xl bg-surface-container p-xl"
    >
      {/* Issue 371 item 9: the mock's two graph cards both carry a plain
          static label, but only 全体の進捗 had one and the donut header was
          empty. `全テスト` is a fact (the donut counts every test); it is not a
          dropdown, so no chevron. */}
      <div className="flex items-center justify-between gap-md">
        <h2 className="font-semibold text-heading" style={PANEL_TITLE_STYLE}>
          テストの進捗
        </h2>
        <span className="text-ui-label text-on-surface-variant">全テスト</span>
      </div>
      <div className="mt-lg">
        <HomeDonutChart slices={slices} total={total} />
      </div>
    </section>
  );
}
