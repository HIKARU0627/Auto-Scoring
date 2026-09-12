import type { JSX } from "react";

import {
  MATERIAL_SYMBOL_PATHS,
  MATERIAL_SYMBOL_VIEW_BOX,
  type MaterialSymbolName,
} from "./material-symbols.js";

/**
 * A single Material Symbols glyph, inlined as SVG (Issue #392).
 *
 * Replaces the `material-symbols-outlined` ligature font, which was never
 * shipped: the ligature name rendered as text ("check_circle") because the CSP
 * forbids loading any font. An SVG path always draws, so there is no "the font
 * did not load" state in which a name leaks into the UI.
 *
 * Size follows `font-size` (`1em`) so an icon rides the same type scale as the
 * text it sits beside -- `text-5xl` on the startup error screen, the label size
 * in a status badge -- instead of a size nobody chose. Colour is `currentColor`,
 * so a call site keeps colouring the icon with its existing token utility.
 *
 * `label` is required and becomes the accessible name. An icon that carries
 * meaning must never be an unlabelled graphic, and one that is purely
 * decorative should be hidden by the call site if the adjacent text already
 * says it.
 */
export interface MaterialSymbolIconProps {
  readonly name: MaterialSymbolName;
  /** Accessible name for the glyph itself. */
  readonly label: string;
  readonly className?: string;
  readonly testId?: string | undefined;
}

export function MaterialSymbolIcon({
  name,
  label,
  className,
  testId,
}: MaterialSymbolIconProps): JSX.Element {
  return (
    <svg
      role="img"
      aria-label={label}
      data-icon={name}
      data-testid={testId}
      width="1em"
      height="1em"
      viewBox={MATERIAL_SYMBOL_VIEW_BOX}
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <path d={MATERIAL_SYMBOL_PATHS[name]} />
    </svg>
  );
}
