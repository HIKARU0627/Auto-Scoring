import type { JSX } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type BarShapeProps,
} from "recharts";

import type { HomeDailyPoint } from "../../../core/home-analytics.js";

/**
 * Daily intake bar chart (Issue #336). Recharts draws SVG, so each bar is a
 * real DOM node: the regression test reads `data-count` and the computed
 * `height` off the bars instead of screenshotting a canvas.
 *
 * The bar is drawn by `DailyBarShape` rather than the default rectangle for
 * exactly that reason -- the default hides the value in a path `d`, which a
 * test cannot compare without re-implementing the geometry.
 */
function DailyBarShape({
  x,
  y,
  width,
  height,
  payload,
}: BarShapeProps): JSX.Element {
  const point = payload as Partial<HomeDailyPoint> | undefined;
  const count = point?.count ?? 0;
  const doneCount = point?.doneCount ?? 0;
  const openCount = count - doneCount;
  // The mock stacks two series with both heights variable (Issue 366): the
  // confirmed answers at the bottom, the still-open ones above. Both come from
  // `submission.state`, so the split is measured, not invented.
  const openHeight = count > 0 ? (height * openCount) / count : 0;
  return (
    <g>
      <rect
        data-testid="home-daily-bar"
        data-count={count}
        data-done-count={doneCount}
        x={x}
        y={y}
        width={width}
        height={height}
        rx={4}
        fill="var(--color-primary)"
      />
      {openCount > 0 ? (
        <rect
          data-testid="home-daily-bar-open"
          x={x}
          y={y}
          width={width}
          height={openHeight}
          rx={4}
          fill="var(--color-outline-variant)"
        />
      ) : null}
    </g>
  );
}

const TOOLTIP_CONTENT_STYLE = {
  background: "var(--color-surface-container-high)",
  border: "1px solid var(--color-outline-variant)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-on-surface)",
} as const;

export function HomeBarChart({
  points,
}: {
  points: readonly HomeDailyPoint[];
}): JSX.Element {
  const total = points.reduce((sum, point) => sum + point.count, 0);
  const doneTotal = points.reduce((sum, point) => sum + point.doneCount, 0);
  return (
    <figure
      data-testid="home-daily-chart"
      role="img"
      aria-label={`直近${points.length}日の答案取込数。合計${total}件、うち確認済み${doneTotal}件。`}
      className="flex h-full min-h-36 min-w-0 flex-col"
      style={{ margin: 0 }}
    >
      {/* Issue 366 item 5: the card stretches to the donut card beside it, so
          the plot takes the leftover height instead of leaving it as dead
          space under the axis. `min-h-36` keeps the plot (Issue 360's ~110px
          plot plus its labels) even before a stretch and in jsdom, where
          nothing is measured. */}
      <div data-testid="home-daily-plot" className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={[...points]}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
            accessibilityLayer={false}
          >
            {/* Two dark grid lines and a brighter zero baseline, the mock's
                measured strokes (Issue 366 item 1). */}
            <CartesianGrid vertical={false} stroke="var(--color-chart-grid)" />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={{ stroke: "var(--color-chart-axis)" }}
              tick={{
                fill: "var(--color-on-surface-variant)",
                fontSize: 12,
              }}
            />
            <YAxis
              domain={[0, "dataMax"]}
              allowDecimals={false}
              width={28}
              tickLine={false}
              axisLine={false}
              tick={{
                fill: "var(--color-on-surface-variant)",
                fontSize: 12,
              }}
            />
            <Tooltip
              cursor={{ fill: "var(--color-surface-container-high)" }}
              contentStyle={TOOLTIP_CONTENT_STYLE}
              formatter={(value) => [`${String(value)}件`, "取込"]}
            />
            {/* Without a cap Recharts widens a lone bar to fill the category
                (measured 87px); the mock is a 23px bar on a 64px pitch
                (Issue 353, evaluation A). */}
            <Bar
              dataKey="count"
              fill="var(--color-primary)"
              shape={DailyBarShape}
              isAnimationActive={false}
              maxBarSize={28}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {/* The numbers are also readable without the SVG: the chart is a picture
          of this list, not the only copy of it. The two stacked series are
          spelled out too, so the split is not carried by colour alone. */}
      <figcaption className="sr-only">
        {points
          .map(
            (point) =>
              `${point.label} ${point.count}件（確認済み${point.doneCount}件）`,
          )
          .join("、")}
      </figcaption>
    </figure>
  );
}
