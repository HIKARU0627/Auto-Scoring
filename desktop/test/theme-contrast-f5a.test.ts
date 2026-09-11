import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import * as path from "node:path";

import {
  AA_NON_TEXT,
  AA_TEXT,
  contrast,
  parseHexColor,
} from "../src/shared/contrast";
import {
  readThemeTokens,
  tokenHex,
  type ThemeName,
} from "./support/read-design-tokens";

/**
 * Issue #371 (stage F5A, parent #333): the text-hierarchy token contract.
 *
 * The accent-text ratio is pinned numerically because the 5th-round evaluation
 * measured the old `--color-primary` text at 3.0:1 on the card, below WCAG AA.
 * The secondary ramp and the state-colour nudges are pinned by value so a
 * future palette pass cannot silently collapse them again.
 */

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const BRIDGE_PATH = path.join(PACKAGE_ROOT, "src/renderer/styles/index.css");
const THEMES = ["light", "dark"] as const satisfies readonly ThemeName[];

const NEW_COLOR_TOKENS = [
  "--color-primary-text",
  "--color-heading",
  "--color-on-surface-strong",
  "--color-on-surface-muted",
] as const;

function color(tokens: Map<string, string>, name: `--${string}`) {
  return parseHexColor(tokenHex(tokens, name));
}

function expectBridged(bridge: string, token: string): void {
  expect(
    bridge,
    `${token} が index.css の @theme inline にブリッジされていない`,
  ).toMatch(new RegExp(`${token}:\\s*var\\(${token}\\)`));
}

describe("accent text is readable on every card it sits on (Issue #371 item 1)", () => {
  for (const theme of THEMES) {
    const tokens = readThemeTokens(theme);

    it(`${theme}: accent text clears AA where the home screen uses it`, () => {
      const accent = color(tokens, "--color-primary-text");
      for (const surfaceToken of [
        "--color-surface-container",
        "--color-surface-container-high",
      ] as const) {
        expect(
          contrast(accent, color(tokens, surfaceToken)),
          `primary-text on ${surfaceToken}`,
        ).toBeGreaterThanOrEqual(AA_TEXT);
      }
    });
  }

  it("dark: the fill token alone was below AA, so the text token is required", () => {
    const tokens = readThemeTokens("dark");
    expect(
      contrast(
        color(tokens, "--color-primary"),
        color(tokens, "--color-surface-container"),
      ),
      "the fill --color-primary used as text",
    ).toBeLessThan(AA_TEXT);
  });

  it("keeps the sampled mock lavender on the default (dark) theme", () => {
    expect(tokenHex(readThemeTokens("dark"), "--color-primary-text")).toBe(
      "#8d92f9",
    );
  });
});

describe("secondary text and headings are a measured ramp (Issue #371 items 2-3)", () => {
  for (const theme of THEMES) {
    const tokens = readThemeTokens(theme);

    it(`${theme}: every secondary tier clears AA on the card surfaces`, () => {
      for (const token of [
        "--color-heading",
        "--color-on-surface-strong",
        "--color-on-surface-muted",
      ] as const) {
        for (const surfaceToken of [
          "--color-surface-container",
          "--color-surface-container-high",
        ] as const) {
          expect(
            contrast(color(tokens, token), color(tokens, surfaceToken)),
            `${token} on ${surfaceToken}`,
          ).toBeGreaterThanOrEqual(AA_TEXT);
        }
      }
    });
  }

  it("dark: the mock's heading is pure white and the muted/strong steps differ", () => {
    const tokens = readThemeTokens("dark");
    expect(tokenHex(tokens, "--color-heading")).toBe("#ffffff");
    const strong = color(tokens, "--color-on-surface-strong");
    const variant = color(tokens, "--color-on-surface-variant");
    const muted = color(tokens, "--color-on-surface-muted");
    // Three distinct steps, ordered prominent -> quiet.
    const luma = (rgb: { r: number; g: number; b: number }) =>
      rgb.r * 0.2126 + rgb.g * 0.7152 + rgb.b * 0.0722;
    expect(luma(strong)).toBeGreaterThan(luma(variant));
    expect(luma(variant)).toBeGreaterThan(luma(muted));
  });
});

describe("state colours move toward the mock without breaking AA (Issue #371 item 4)", () => {
  it("dark: info takes the mock blue as a non-text dot", () => {
    expect(tokenHex(readThemeTokens("dark"), "--color-info")).toBe("#5784fa");
    const tokens = readThemeTokens("dark");
    expect(
      contrast(
        color(tokens, "--color-info"),
        color(tokens, "--color-surface-container"),
      ),
      "info dot on the card",
    ).toBeGreaterThanOrEqual(AA_NON_TEXT);
  });

  it("dark: attention keeps AA while moving off the old pale pink", () => {
    const tokens = readThemeTokens("dark");
    expect(tokenHex(tokens, "--color-attention")).not.toBe("#ff7ba8");
    expect(tokenHex(tokens, "--color-attention")).toBe("#fe74a3");
    expect(
      contrast(
        color(tokens, "--color-attention"),
        color(tokens, "--color-surface-container-highest"),
      ),
      "attention text on the lightest card",
    ).toBeGreaterThanOrEqual(AA_TEXT);
  });
});

describe("the KPI column rule is the number block's height (Issue #371 item 8)", () => {
  it("defines 50px and exposes the h-kpi-rule utility", () => {
    expect(tokenHex(readThemeTokens("dark"), "--layout-kpi-rule-height")).toBe(
      "50px",
    );
    const bridge = readFileSync(BRIDGE_PATH, "utf8");
    expect(bridge).toMatch(
      /\.h-kpi-rule\s*\{\s*height:\s*var\(--layout-kpi-rule-height\)/,
    );
  });
});

describe("the new text tokens are bridged into Tailwind (Issue #371)", () => {
  it("every new colour token is defined in light and dark and bridged", () => {
    const bridge = readFileSync(BRIDGE_PATH, "utf8");
    for (const theme of THEMES) {
      const tokens = readThemeTokens(theme);
      for (const token of NEW_COLOR_TOKENS) {
        expect(tokenHex(tokens, token).length, `${theme}: ${token} が空`).toBe(
          7,
        );
      }
    }
    for (const token of NEW_COLOR_TOKENS) {
      expectBridged(bridge, token);
    }
  });
});
