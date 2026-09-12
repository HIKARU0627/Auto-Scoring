import type { CSSProperties } from "react";

import type { HomeTestStatusBadge } from "../../core/home-dashboard.js";

/**
 * Shared presentation helpers for the home dashboard (Issue #336).
 *
 * Tone names come from `HomeWorkBucket` / `HomeTestPhase`; the class strings
 * here are the only place that maps them to tokens, so a state cannot be
 * coloured differently in two panels.
 */

/** `--font-variant-numeric-score` (tabular-nums) for every number on screen. */
export const NUMERIC_STYLE: CSSProperties = {
  fontVariantNumeric: "var(--font-variant-numeric-score)",
};

/**
 * Panel heading size (Issue #353). The token layer maps no `text-title-*`
 * utility between body (14px) and title-large (22px), and `features/` may not
 * add one, so this derives 17.5px from the body token. The mock's panel
 * headings measure 17.6px; before this the heading equalled the body text and
 * the hierarchy collapsed (parent #333 evaluation A).
 */
export const PANEL_TITLE_STYLE: CSSProperties = {
  fontSize: "calc(var(--font-size-body-medium) * 1.25)",
};

/** Table header size (Issue #353): the mock's header is quieter than the body. */
export const TABLE_HEAD_STYLE: CSSProperties = {
  fontSize: "var(--font-size-label-medium)",
};

/**
 * Status-pill height (Issue 365): the mock's pill is 24px inside a 43px row.
 * The horizontal padding is the `px-lg` class on the pill (Issue 372), not a
 * value here, so the two themes share one rule.
 */
export const STATUS_PILL_STYLE: CSSProperties = {
  height: "25px",
};

/**
 * Recent-tests column widths (Issue #372, parent Issue 333; Issue #375 items
 * 2/17). The widths are percentages because Tailwind has no such fraction. The
 * mock's measured split is 21/23/11/22/16/7, and the old build kept that shape
 * while the table spanned the full page: that left 状態 as the second
 * widest column (272px) for a badge plus one "取込済み N件" line, and pushed the
 * 答案数↔進捗 gap to ~2.5x the 進捗↔最終更新 gap.
 *
 * Issue #375 widens テスト名 (the column that should absorb long names), narrows
 * 状態 to a badge-sized share, and brings 答案数 / 進捗 within a 1.5:1 gap ratio
 * (item 2). `updated` keeps the mock's weight next to the date column.
 */
export const TABLE_COLUMN_WIDTH_STYLE: {
  readonly name: CSSProperties;
  readonly status: CSSProperties;
  readonly answer: CSSProperties;
  readonly progress: CSSProperties;
  readonly updated: CSSProperties;
  readonly open: CSSProperties;
} = {
  name: { width: "23%" },
  status: { width: "15%" },
  answer: { width: "15%" },
  progress: { width: "19%" },
  updated: { width: "21%" },
  open: { width: "7%" },
};

/**
 * 全体の進捗 KPI number (Issue 360). At 24px it read as another panel heading;
 * the mock's number is 22px against an 18px heading (1.22x). Our heading is
 * 17.5px, so 1.4x title-large lands at ~30.8px -- the mock's "30px級".
 */
export const KPI_VALUE_STYLE: CSSProperties = {
  fontSize: "calc(var(--font-size-title-large) * 1.4)",
};

/**
 * 全体の進捗 KPI number indent (Issue #375 item 12). The mock left-aligns the
 * big number with the *label text* (both at x=301), not with the tone dot; the
 * build aligned it to the dot, so the number hung 24px to the left of its
 * label. The dot is `size-4` (16px) plus the `gap-sm` (8px) before the label,
 * which is the 24px here.
 */
export const KPI_NUMBER_INDENT_STYLE: CSSProperties = {
  paddingLeft: "var(--spacing-xl)",
};

/**
 * Quick-action subtitle (Issue 360). The heading and subtitle both measured
 * 14px, so the two stacked lines read as one paragraph and the row grew to
 * 82px. Dropping the subtitle to the body-small token gives the 12px step.
 */
export const QUICK_ACTION_SUBTITLE_STYLE: CSSProperties = {
  fontSize: "var(--font-size-body-small)",
};

export function toneDotClass(tone: string): string {
  switch (tone) {
    case "attention":
      return "bg-attention";
    case "primary":
      return "bg-primary";
    case "info":
      return "bg-info";
    case "success":
      return "bg-success";
    case "danger":
    case "error":
      return "bg-error";
    default:
      return "bg-outline";
  }
}

export function toneTextClass(tone: string): string {
  switch (tone) {
    case "attention":
      return "text-attention";
    case "info":
      return "text-info";
    case "success":
      return "text-success";
    case "danger":
    case "error":
      return "text-error";
    default:
      return "text-on-surface-variant";
  }
}

/**
 * Status pill fills (Issue #353, parent #333). Each tone is a *solid* vivid
 * token so the state is legible against the card; the old `*-container` fills
 * sank into the card (info-container `#1f3a72` vs card `#232b3e`) and only the
 * label carried the state. The foreground is paired per tone so the text
 * contrast survives both themes: `text-surface` is dark in the dark theme and
 * light in the light theme, which is what the light status hues need.
 */
export function statusPillClass(badge: HomeTestStatusBadge): string {
  switch (badge.tone) {
    case "attention":
      return "bg-attention text-surface";
    case "info":
      return "bg-primary text-on-primary";
    case "success":
      return "bg-success text-surface";
    case "danger":
    case "error":
      return "bg-error-container text-on-error-container";
    case "muted":
      return "bg-secondary-container text-on-secondary-container";
    case "neutral":
      return "bg-outline text-surface";
    default:
      return "bg-outline text-surface";
  }
}

/**
 * Recharts `paddingAngle` for the test donut (Issue #353). A non-zero gap only
 * makes sense *between* sectors: with one non-zero sector the ring is a full
 * circle, and any padding shows up as a bite taken out of the top of the ring.
 */
export function donutPaddingAngle(
  slices: readonly { readonly count: number }[],
): number {
  return slices.filter((slice) => slice.count > 0).length > 1 ? 2 : 0;
}

/** Fill token per donut phase; `preparing` is the sunk grey (Issue #375 item 15). */
export function phaseFill(phase: string): string {
  switch (phase) {
    case "inProgress":
      return "var(--color-primary)";
    case "done":
      return "var(--color-success)";
    default:
      return "var(--color-phase-preparing)";
  }
}
