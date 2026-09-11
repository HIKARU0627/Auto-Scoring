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
      className="min-w-0 rounded-xl bg-surface-container p-lg"
    >
      <h2 className="text-body-medium font-semibold text-on-surface">
        テストの進捗
      </h2>
      <div className="mt-lg">
        <HomeDonutChart slices={slices} total={total} />
      </div>
    </section>
  );
}
