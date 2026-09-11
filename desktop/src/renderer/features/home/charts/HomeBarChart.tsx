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
  const count = (payload as { count?: number } | undefined)?.count ?? 0;
  return (
    <rect
      data-testid="home-daily-bar"
      data-count={count}
      x={x}
      y={y}
      width={width}
      height={height}
      rx={4}
      fill="var(--color-primary)"
    />
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
  return (
    <figure
      data-testid="home-daily-chart"
      role="img"
      aria-label={`直近${points.length}日の答案取込数。合計${total}件。`}
      className="min-w-0"
      style={{ margin: 0 }}
    >
      <ResponsiveContainer width="100%" height={200}>
        <BarChart
          data={[...points]}
          margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          accessibilityLayer={false}
        >
          <CartesianGrid
            vertical={false}
            stroke="var(--color-outline-variant)"
          />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
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
          <Bar
            dataKey="count"
            fill="var(--color-primary)"
            shape={DailyBarShape}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
      {/* The numbers are also readable without the SVG: the chart is a picture
          of this list, not the only copy of it. */}
      <figcaption className="sr-only">
        {points.map((point) => `${point.label} ${point.count}件`).join("、")}
      </figcaption>
    </figure>
  );
}
