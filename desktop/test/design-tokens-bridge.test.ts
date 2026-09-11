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

/** Issue #361: the sidebar's own text roles, sampled from the mock. */
const SIDEBAR_TOKENS = [
  "--color-sidebar-subtitle",
  "--color-sidebar-nav-idle",
] as const;

/** Issue #361: scrollbar colours are aliases resolved per theme. */
const SCROLLBAR_TOKENS = [
  "--color-scrollbar-thumb",
  "--color-scrollbar-track",
] as const;

/** Issue #361: headline step utilities the `features/` layer can migrate onto. */
const HEADLINE_TEXT_TOKENS = [
  ["--text-headline-large", "--font-size-headline-large"],
  ["--text-headline-medium", "--font-size-headline-medium"],
  ["--text-headline-small", "--font-size-headline-small"],
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

describe("sidebar text roles (Issue #361)", () => {
  it("both sidebar roles are defined in light and dark", () => {
    for (const theme of THEMES) {
      const tokens = readThemeTokens(theme);
      for (const token of SIDEBAR_TOKENS) {
        expect(
          tokenHex(tokens, token).length,
          `${theme}: ${token} が空`,
        ).toBeGreaterThan(0);
      }
    }
  });

  it("both sidebar roles are bridged into Tailwind", () => {
    const bridge = readFileSync(BRIDGE_PATH, "utf8");
    for (const token of SIDEBAR_TOKENS) {
      expectBridged(bridge, token);
    }
  });

  it("keeps the sampled mock values on the default (dark) theme", () => {
    const tokens = readThemeTokens("dark");
    expect(tokenHex(tokens, "--color-sidebar-subtitle")).toBe("#8493af");
    expect(tokenHex(tokens, "--color-sidebar-nav-idle")).toBe("#9facd7");
  });
});

describe("scrollbar theme (Issue #361)", () => {
  it("paints the scrollbar from palette alias tokens", () => {
    const bridge = readFileSync(BRIDGE_PATH, "utf8");
    expect(bridge).toMatch(
      /scrollbar-color:\s*var\(--color-scrollbar-thumb\)\s+var\(--color-scrollbar-track\)/,
    );
  });

  it("both scrollbar aliases resolve in light and dark", () => {
    for (const theme of THEMES) {
      const tokens = readThemeTokens(theme);
      for (const token of SCROLLBAR_TOKENS) {
        expect(
          tokenHex(tokens, token).length,
          `${theme}: ${token} が空`,
        ).toBeGreaterThan(0);
      }
    }
  });
});

describe("headline text utilities (Issue #361)", () => {
  it("bridges text-headline-* to the font-size tokens", () => {
    const bridge = readFileSync(BRIDGE_PATH, "utf8");
    for (const [utility, sizeToken] of HEADLINE_TEXT_TOKENS) {
      expect(
        bridge,
        `${utility} が ${sizeToken} へブリッジされていない`,
      ).toMatch(new RegExp(`${utility}:\\s*var\\(${sizeToken}\\)`));
    }
  });

  it("the underlying font-size tokens are defined", () => {
    const tokens = readThemeTokens("dark");
    for (const [, sizeToken] of HEADLINE_TEXT_TOKENS) {
      expect(
        tokenHex(tokens, sizeToken).length,
        `${sizeToken} が未定義`,
      ).toBeGreaterThan(0);
    }
  });
});
