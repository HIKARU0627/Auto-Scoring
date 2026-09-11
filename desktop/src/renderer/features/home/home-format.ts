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

export function statusPillClass(badge: HomeTestStatusBadge): string {
  switch (badge.tone) {
    case "attention":
      return "bg-attention-container text-on-attention-container";
    case "info":
      return "bg-info-container text-on-info-container";
    case "success":
      return "bg-success-container text-on-success-container";
    case "danger":
    case "error":
      return "bg-error-container text-on-error-container";
    default:
      return "bg-surface-container-high text-on-surface-variant";
  }
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
