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
 * Mock-measured recent-tests row metrics (Issue 365, parent Issue 333). The
 * mock table is one 43px row whose status pill is 73x25px, and its progress
 * track measures 148px. Keeping the track at 140px makes it dominate the 進捗
 * cell, and pinning the pill's height stops the old `py-xs` (32px) from
 * dropping the bucket counts onto a second line.
 */
export const PROGRESS_TRACK_STYLE: CSSProperties = {
  width: "8.75rem",
};

export const STATUS_PILL_STYLE: CSSProperties = {
  height: "25px",
};

/**
 * The mock's test name is body weight (32.1% ink against the bold 44.5%) and
 * leaves 92px of slack in a ~200px column, so the name is capped and ellipsized
 * instead of growing to 173px and squeezing the status column to 31px.
 */
export const TEST_NAME_STYLE: CSSProperties = {
  maxWidth: "9rem",
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

/** Fill token per donut phase; `preparing` is grey like the mock. */
export function phaseFill(phase: string): string {
  switch (phase) {
    case "inProgress":
      return "var(--color-primary)";
    case "done":
      return "var(--color-success)";
    default:
      return "var(--color-outline)";
  }
}
