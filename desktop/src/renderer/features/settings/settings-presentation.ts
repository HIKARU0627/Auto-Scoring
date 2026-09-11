import type { CSSProperties } from "react";

/**
 * Shared presentation for the settings screen (Issue #347).
 *
 * The mock (parent #333) separates information with a rounded surface, not a
 * border, so every card here is `--radius-xl` on `--color-surface-container`.
 * Class strings live in one place so the two tabs cannot drift apart and so a
 * state's colour is decided once.
 */

export const NUMERIC_STYLE: CSSProperties = {
  fontVariantNumeric: "var(--font-variant-numeric-score)",
};

export const SETTINGS_CARD_CLASS =
  "min-w-0 rounded-xl bg-surface-container p-lg";

export const SETTINGS_BUTTON_PRIMARY_CLASS =
  "inline-flex items-center gap-xs rounded-md bg-primary px-md py-sm text-ui-label font-medium text-on-primary hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-80 disabled:opacity-50";

export const SETTINGS_BUTTON_SECONDARY_CLASS =
  "inline-flex items-center gap-xs rounded-md border border-outline px-md py-sm text-ui-label font-medium text-on-surface hover:bg-surface-container-high focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-80 disabled:opacity-50";

export const SETTINGS_BUTTON_DANGER_CLASS =
  "inline-flex items-center gap-xs rounded-md px-md py-sm text-ui-label font-medium text-error hover:bg-error-container/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-error active:opacity-80 disabled:opacity-50";

export const SETTINGS_INPUT_CLASS =
  "mt-xs w-full rounded-md border border-outline bg-surface px-md py-sm text-body-medium text-on-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary";

export const SETTINGS_SELECT_CLASS =
  "mt-xs w-full rounded-md border border-outline bg-surface px-md py-sm text-body-medium text-on-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary";

export const SETTINGS_LABEL_CLASS =
  "block text-ui-label font-medium text-on-surface";

/** Short, colour-independent state pill for one API key slot. */
export function apiKeyStatePillClass(configured: boolean): string {
  return configured
    ? "inline-flex shrink-0 items-center gap-xs rounded-full bg-success-container px-sm py-xs text-ui-label text-on-success-container"
    : "inline-flex shrink-0 items-center gap-xs rounded-full bg-surface-container-high px-sm py-xs text-ui-label text-on-surface-variant";
}

export function apiKeyVerificationCardClass(ok: boolean): string {
  return ok
    ? "mt-md flex items-start gap-sm rounded-lg bg-success-container/40 p-sm text-on-success-container"
    : "mt-md flex items-start gap-sm rounded-lg bg-error-container/40 p-sm text-on-error-container";
}
