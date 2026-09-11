import type { JSX } from "react";
import { Pie, PieChart, ResponsiveContainer } from "recharts";

import type { HomeTestPhase } from "../../../core/home-dashboard.js";
import { donutPaddingAngle, NUMERIC_STYLE, phaseFill } from "../home-format.js";

export interface HomePhaseSlice {
  readonly phase: HomeTestPhase;
  readonly label: string;
  readonly count: number;
  readonly percent: number;
}

/**
 * Test-status donut (Issue #336). Recharts draws an SVG `<path>` per non-zero
 * slice, and the legend repeats each slice as text, so neither the colour nor
 * the shape is the only carrier of the number.
 */
export function HomeDonutChart({
  slices,
  total,
}: {
  slices: readonly HomePhaseSlice[];
  total: number;
}): JSX.Element {
  const chartData = slices.map((slice) => ({
    name: slice.label,
    value: slice.count,
    fill: phaseFill(slice.phase),
  }));
  const summary = slices
    .map((slice) => `${slice.label}${slice.count}件`)
    .join("、");
  const paddingAngle = donutPaddingAngle(slices);
  const singleSector = paddingAngle === 0;
  // A surface-coloured stroke on a lone 100% sector draws the card colour
  // across the ring's seam, so a full ring is drawn without a stroke.
  const sectorStroke = singleSector ? "none" : "var(--color-surface-container)";
  // Measured from the mock (Issue 366 item 4): 150px outer diameter and a
  // 23px ring -> radii 75 / 52, down from the 165 / 25 the code drew before.

  return (
    <div
      data-testid="home-phase-chart"
      data-padding-angle={paddingAngle}
      className="flex min-w-0 flex-col gap-md max-lg:flex-row max-lg:items-center"
    >
      {/* Issue 371 item 10: in the 700px single column the card is ~548px and
          the 150px donut left ~200px dead on each side. Below `lg` the legend
          moves beside the ring and takes the spare width; the ring geometry
          itself is the mock's 150/23 (radii 75/52) at every width. */}
      <div
        role="img"
        aria-label={`テストの進捗。${summary}。合計${total}テスト。`}
        className="relative h-48 w-full max-lg:w-44 max-lg:shrink-0"
      >
        <ResponsiveContainer width="100%" height="100%">
          <PieChart accessibilityLayer={false}>
            <Pie
              data={chartData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={52}
              outerRadius={75}
              startAngle={90}
              endAngle={-270}
              paddingAngle={paddingAngle}
              isAnimationActive={false}
              stroke={sectorStroke}
              rootTabIndex={-1}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span
            data-testid="home-phase-total"
            className="text-score font-semibold"
            style={NUMERIC_STYLE}
          >
            {total}
          </span>
          <span className="text-ui-label text-on-surface-variant">テスト</span>
        </div>
      </div>
      <ul
        data-testid="home-phase-legend"
        className="flex min-w-0 flex-col gap-sm max-lg:flex-1"
      >
        {slices.map((slice) => (
          <li
            key={slice.phase}
            data-testid={`home-phase-${slice.phase}`}
            className="flex items-center gap-sm text-body-medium leading-tight"
          >
            <span
              aria-hidden
              className="size-4 shrink-0 rounded-full"
              style={{ background: phaseFill(slice.phase) }}
            />
            {/* Issue 360: the mock's legend is two columns -- the count lives
                inside the label as `準備中 (3)`, and the percent sits alone on
                the right. The old three-column form read label / count / %. */}
            <span
              style={NUMERIC_STYLE}
              className="min-w-0 flex-1 truncate text-on-surface"
            >
              {slice.label} ({slice.count})
            </span>
            <span
              style={NUMERIC_STYLE}
              className="w-12 shrink-0 text-right tabular-nums text-on-surface-variant"
            >
              {slice.percent}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
