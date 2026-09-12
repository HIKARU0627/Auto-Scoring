import type { CSSProperties } from "react";

/**
 * Shared presentation for the settings screen (Issue #347, parent #333).
 *
 * The mock separates information with a rounded surface, not a border, so
 * every card here is `--radius-xl` on `--color-surface-container` and every
 * secondary control is a filled surface rather than an outline. Class strings
 * live in one place so the two tabs cannot drift apart and so a state's colour
 * is decided once.
 */

export const NUMERIC_STYLE: CSSProperties = {
  fontVariantNumeric: "var(--font-variant-numeric-score)",
};

export const SETTINGS_CARD_CLASS =
  "min-w-0 rounded-xl bg-surface-container p-lg";

/** 20px card heading: the mock keeps four text levels (20 / 16 / 14 / 12). */
export const SETTINGS_CARD_HEADING_CLASS =
  "text-xl font-semibold leading-ui text-on-surface";

export const SETTINGS_ITEM_HEADING_CLASS =
  "text-base font-semibold leading-ui text-on-surface";

export const SETTINGS_BUTTON_PRIMARY_CLASS =
  "inline-flex items-center gap-xs rounded-md bg-primary px-md py-sm text-ui-label font-medium text-on-primary hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-80 disabled:opacity-50";

/** Filled, not outlined: the mock has no outline-only button (parent #333 §2). */
export const SETTINGS_BUTTON_SECONDARY_CLASS =
  "inline-flex items-center gap-xs rounded-md bg-surface-container-high px-md py-sm text-ui-label font-medium text-on-surface hover:bg-surface-container-highest focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-80 disabled:opacity-50";

export const SETTINGS_BUTTON_DANGER_CLASS =
  "inline-flex items-center gap-xs rounded-md px-md py-sm text-ui-label font-medium text-error hover:bg-error-container/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-error active:opacity-80 disabled:opacity-50";

export const SETTINGS_INPUT_CLASS =
  "mt-xs w-full rounded-md bg-surface-container-high px-md py-sm text-body-medium text-on-surface placeholder:text-on-surface-variant focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary";

export const SETTINGS_SELECT_CLASS =
  "mt-xs w-full rounded-md bg-surface-container-high px-md py-sm text-body-medium text-on-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary";

export const SETTINGS_LABEL_CLASS =
  "block text-ui-label font-medium text-on-surface";

/** Purple rounded tile + glyph for empty/leading icons (parent #333 §9). */
export const SETTINGS_ICON_TILE_CLASS =
  "inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-container text-on-primary-container";

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

/** One row of the "use order" list (Issue #386, Issue #448).
 *
 * The drag state is carried by *shape* as well as colour: a row being dragged
 * gets a dashed outline and is faded, and the row it would land on gets a
 * solid outline and a raised surface. A person who cannot tell the two hues
 * apart can still follow the gesture by the outline pattern and the fade.
 */
export function transportOrderItemClass(
  state: { dragging?: boolean; dropTarget?: boolean } = {},
): string {
  const base =
    "flex items-center gap-xs rounded-md bg-surface-container-high px-sm py-xs text-body-medium text-on-surface";
  if (state.dragging) {
    return `${base} opacity-60 outline outline-2 outline-dashed outline-primary`;
  }
  if (state.dropTarget) {
    return `${base} bg-surface-container-highest outline outline-2 outline-primary`;
  }
  return base;
}

/** The grab handle of one "use order" row: the only draggable part of it.
 *
 * `aria-hidden` on purpose: dragging is a pointer-only gesture, and the
 * screen-reader path to the same reorder is the 「上へ」「下へ」 buttons that
 * sit next to it (Issue #448 requires the keyboard path to survive).
 */
export const TRANSPORT_ORDER_HANDLE_CLASS =
  "inline-flex size-6 shrink-0 cursor-grab items-center justify-center rounded-sm text-on-surface-variant hover:bg-surface-container-highest focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:cursor-grabbing";
