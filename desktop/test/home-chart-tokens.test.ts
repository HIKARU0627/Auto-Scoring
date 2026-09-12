import { readFileSync } from "node:fs";
import * as path from "node:path";
import { describe, expect, it } from "vitest";

import {
  readThemeTokens,
  tokenHex,
  type ThemeName,
} from "./support/read-design-tokens";

/**
 * Issue #366 (stage F4B, parent #333): the chart strokes measured from the
 * mock must live in the token layer, not in the JSX (INV-080), and every one
 * must be bridged into Tailwind so a utility (`border-chart-divider`) resolves.
 *
 * The values are decorative separators; like `--color-outline-variant` they are
 * not held to the 3:1 UI-component minimum (docs/design-tokens.md §3.5).
 */

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const BRIDGE_PATH = path.join(PACKAGE_ROOT, "src/renderer/styles/index.css");
const THEMES = ["light", "dark"] as const satisfies readonly ThemeName[];

const CHART_TOKENS = [
  "--color-chart-grid",
  "--color-chart-axis",
  "--color-chart-divider",
  // Issue #375 items 15-16: the y-axis label step and the sunk 準備中 mark.
  "--color-chart-label-secondary",
  "--color-phase-preparing",
] as const;

describe("home chart tokens (Issue #366)", () => {
  it("defines every chart stroke in light and dark", () => {
    for (const theme of THEMES) {
      const tokens = readThemeTokens(theme);
      for (const token of CHART_TOKENS) {
        expect(
          tokenHex(tokens, token),
          `${theme}: ${token} must be a colour literal`,
        ).toMatch(/^#[0-9a-f]{6}$/i);
      }
    }
  });

  it("bridges every chart stroke into Tailwind", () => {
    const bridge = readFileSync(BRIDGE_PATH, "utf8");
    for (const token of CHART_TOKENS) {
      expect(
        bridge,
        `${token} が index.css の @theme inline にブリッジされていない`,
      ).toMatch(new RegExp(`${token}:\\s*var\\(${token}\\)`));
    }
  });
});
