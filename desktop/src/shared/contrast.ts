/**
 * WCAG 2.1 contrast helpers — same thresholds as
 * `app/test/app_theme_contrast_test.dart`.
 */

export const AA_TEXT = 4.5;
export const AA_NON_TEXT = 3.0;

export interface Rgb {
  readonly r: number;
  readonly g: number;
  readonly b: number;
}

/** Parse `#RRGGBB` (case-insensitive). */
export function parseHexColor(hex: string): Rgb {
  const normalized = hex.trim().replace(/^#/, "");
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
    throw new Error(`expected #RRGGBB, got ${hex}`);
  }
  return {
    r: Number.parseInt(normalized.slice(0, 2), 16) / 255,
    g: Number.parseInt(normalized.slice(2, 4), 16) / 255,
    b: Number.parseInt(normalized.slice(4, 6), 16) / 255,
  };
}

function channelLuminance(channel: number): number {
  return channel <= 0.03928
    ? channel / 12.92
    : Math.pow((channel + 0.055) / 1.055, 2.4);
}

/** WCAG 2.1 relative luminance. */
export function luminance(color: Rgb): number {
  return (
    0.2126 * channelLuminance(color.r) +
    0.7152 * channelLuminance(color.g) +
    0.0722 * channelLuminance(color.b)
  );
}

/** WCAG 2.1 contrast ratio, 1.0 (identical) to 21.0 (black on white). */
export function contrast(foreground: Rgb, background: Rgb): number {
  const a = luminance(foreground);
  const b = luminance(background);
  const lighter = Math.max(a, b);
  const darker = Math.min(a, b);
  return (lighter + 0.05) / (darker + 0.05);
}

/** Flutter `Color.alphaBlend(foreground.withAlpha(a), background)` equivalent. */
export function alphaBlend(
  foreground: Rgb,
  alpha: number,
  background: Rgb,
): Rgb {
  const inverse = 1 - alpha;
  return {
    r: foreground.r * alpha + background.r * inverse,
    g: foreground.g * alpha + background.g * inverse,
    b: foreground.b * alpha + background.b * inverse,
  };
}
