import { readFileSync } from "node:fs";
import * as path from "node:path";
import { describe, expect, it } from "vitest";

import {
  readThemeTokens,
  tokenHex,
  type ThemeName,
} from "./support/read-design-tokens";

/**
 * Issue #334 (UI refresh stage A, parent #333): the dark palette sampled from
 * `UI_Home.png` must live in the token layer and be bridged into Tailwind, so
 * the stage B/C screens can reference it without hardcoding values (INV-080).
 *
 * `:root` is the dark default; `[data-theme="light"]` is the kept light theme.
 * The dark block therefore carries the shared non-colour tokens (spacing,
 * radius, fonts) that light inherits, so `--radius-xl` is asserted against the
 * default block only.
 */

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const BRIDGE_PATH = path.join(PACKAGE_ROOT, "src/renderer/styles/index.css");
const TOKENS_PATH = path.join(
  PACKAGE_ROOT,
  "src/renderer/styles/design-tokens.css",
);

const THEMES = ["light", "dark"] as const satisfies readonly ThemeName[];

/** New colour roles introduced by the mock palette. */
const PALETTE_TOKENS = [
  "--color-info",
  "--color-info-container",
  "--color-on-info-container",
  "--color-progress-track",
] as const;

function expectBridged(bridge: string, token: string): void {
  expect(
    bridge,
    `${token} が index.css の @theme inline にブリッジされていない`,
  ).toMatch(new RegExp(`${token}:\\s*var\\(${token}\\)`));
}

describe("mock palette tokens (Issue #334)", () => {
  it("dark is the :root default and light is still defined", () => {
    const css = readFileSync(TOKENS_PATH, "utf8");
    expect(css).toMatch(/:root,\s*\[data-theme="dark"\]\s*\{/);
    expect(css).toMatch(/\[data-theme="light"\]\s*\{/);
  });

  it("every new palette colour is defined in light and dark", () => {
    for (const theme of THEMES) {
      const tokens = readThemeTokens(theme);
      for (const token of PALETTE_TOKENS) {
        expect(
          tokenHex(tokens, token).length,
          `${theme}: ${token} が空`,
        ).toBeGreaterThan(0);
      }
    }
  });

  it("every new palette colour is bridged into Tailwind", () => {
    const bridge = readFileSync(BRIDGE_PATH, "utf8");
    for (const token of PALETTE_TOKENS) {
      expectBridged(bridge, token);
    }
  });

  it("--radius-xl (16px) is defined on the default theme and bridged", () => {
    expect(tokenHex(readThemeTokens("dark"), "--radius-xl")).toBe("16px");
    expectBridged(readFileSync(BRIDGE_PATH, "utf8"), "--radius-xl");
  });
});
