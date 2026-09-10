import { describe, expect, it } from "vitest";
import {
  AA_NON_TEXT,
  AA_TEXT,
  alphaBlend,
  contrast,
  parseHexColor,
} from "../src/shared/contrast";
import {
  readThemeTokens,
  tokenHex,
  type ThemeName,
} from "./support/read-design-tokens";

function color(tokens: Map<string, string>, name: `--${string}`) {
  return parseHexColor(tokenHex(tokens, name));
}

describe("theme contrast", () => {
  for (const themeName of ["light", "dark"] as const satisfies ThemeName[]) {
    const tokens = readThemeTokens(themeName);

    it(`${themeName}: text is readable on every surface step`, () => {
      const onSurface = color(tokens, "--color-on-surface");
      const onSurfaceVariant = color(tokens, "--color-on-surface-variant");
      const surfaces: Record<string, `--${string}`> = {
        surface: "--color-surface",
        surfaceDim: "--color-surface-dim",
        surfaceContainerLowest: "--color-surface-container-lowest",
        surfaceContainerLow: "--color-surface-container-low",
        surfaceContainer: "--color-surface-container",
        surfaceContainerHigh: "--color-surface-container-high",
        surfaceContainerHighest: "--color-surface-container-highest",
      };
      for (const [key, token] of Object.entries(surfaces)) {
        const surface = color(tokens, token);
        expect(
          contrast(onSurface, surface),
          `onSurface on ${key}`,
        ).toBeGreaterThanOrEqual(AA_TEXT);
        expect(
          contrast(onSurfaceVariant, surface),
          `onSurfaceVariant on ${key}`,
        ).toBeGreaterThanOrEqual(AA_TEXT);
      }
    });

    it(`${themeName}: every Material on/role pair meets AA`, () => {
      const pairs: Record<string, [`--${string}`, `--${string}`]> = {
        "onPrimary/primary": ["--color-on-primary", "--color-primary"],
        "onPrimaryContainer/primaryContainer": [
          "--color-on-primary-container",
          "--color-primary-container",
        ],
        "onSecondaryContainer/secondaryContainer": [
          "--color-on-secondary-container",
          "--color-secondary-container",
        ],
        "onTertiaryContainer/tertiaryContainer": [
          "--color-on-tertiary-container",
          "--color-tertiary-container",
        ],
        "onError/error": ["--color-on-error", "--color-error"],
        "onErrorContainer/errorContainer": [
          "--color-on-error-container",
          "--color-error-container",
        ],
        "onInverseSurface/inverseSurface": [
          "--color-on-inverse-surface",
          "--color-inverse-surface",
        ],
      };
      for (const [label, [foregroundToken, backgroundToken]] of Object.entries(
        pairs,
      )) {
        expect(
          contrast(
            color(tokens, foregroundToken),
            color(tokens, backgroundToken),
          ),
          label,
        ).toBeGreaterThanOrEqual(AA_TEXT);
      }
    });

    it(`${themeName}: status colours are readable where they are actually used`, () => {
      const backgrounds: Record<string, `--${string}`> = {
        surface: "--color-surface",
        surfaceContainerLow: "--color-surface-container-low",
        surfaceContainerHighest: "--color-surface-container-highest",
      };
      for (const [key, token] of Object.entries(backgrounds)) {
        const background = color(tokens, token);
        expect(
          contrast(color(tokens, "--color-attention"), background),
          `attention on ${key}`,
        ).toBeGreaterThanOrEqual(AA_TEXT);
        expect(
          contrast(color(tokens, "--color-success"), background),
          `success on ${key}`,
        ).toBeGreaterThanOrEqual(AA_TEXT);
        expect(
          contrast(color(tokens, "--color-error"), background),
          `error on ${key}`,
        ).toBeGreaterThanOrEqual(AA_TEXT);
      }
      expect(
        contrast(
          color(tokens, "--color-on-attention-container"),
          color(tokens, "--color-attention-container"),
        ),
        "onAttentionContainer/attentionContainer",
      ).toBeGreaterThanOrEqual(AA_TEXT);
      expect(
        contrast(
          color(tokens, "--color-on-success-container"),
          color(tokens, "--color-success-container"),
        ),
        "onSuccessContainer/successContainer",
      ).toBeGreaterThanOrEqual(AA_TEXT);
    });

    it(`${themeName}: a disabled button can be found and read`, () => {
      const surfaces: Record<string, `--${string}`> = {
        surface: "--color-surface",
        surfaceContainerLow: "--color-surface-container-low",
        surfaceContainerHigh: "--color-surface-container-high",
        surfaceContainerHighest: "--color-surface-container-highest",
      };
      const outline = color(tokens, "--color-disabled-button-outline");
      const label = color(tokens, "--color-disabled-button-label");
      const container = color(tokens, "--color-disabled-button-container");
      const onSurface = color(tokens, "--color-on-surface");

      for (const [key, token] of Object.entries(surfaces)) {
        const surface = color(tokens, token);
        expect(
          contrast(outline, surface),
          `disabled outline on ${key}`,
        ).toBeGreaterThanOrEqual(AA_NON_TEXT);
        expect(
          contrast(label, surface),
          `disabled label on ${key}`,
        ).toBeGreaterThanOrEqual(AA_TEXT);
      }

      expect(
        contrast(label, container),
        "disabled label on its own container",
      ).toBeGreaterThanOrEqual(AA_TEXT);

      expect(
        contrast(label, color(tokens, "--color-surface-container-low")),
        "disabled label must be quieter than body text",
      ).toBeLessThan(
        contrast(onSurface, color(tokens, "--color-surface-container-low")),
      );
    });

    it(`${themeName}: Material の既定では足りない`, () => {
      const onSurface = color(tokens, "--color-on-surface");
      const surfaceContainerLow = color(
        tokens,
        "--color-surface-container-low",
      );
      const defaultOutline = alphaBlend(onSurface, 0.12, surfaceContainerLow);
      expect(
        contrast(defaultOutline, surfaceContainerLow),
        "Material default disabled outline on a card",
      ).toBeLessThan(AA_NON_TEXT);
    });

    it(`${themeName}: an outline can be found against the surface it bounds`, () => {
      expect(
        contrast(
          color(tokens, "--color-outline"),
          color(tokens, "--color-surface"),
        ),
        "outline on surface",
      ).toBeGreaterThanOrEqual(AA_NON_TEXT);
    });
  }

  it("the annotation mark stays legible on the PDF page, not the theme", () => {
    const light = readThemeTokens("light");
    const dark = readThemeTokens("dark");
    expect(tokenHex(light, "--color-annotation-mark")).toBe(
      tokenHex(dark, "--color-annotation-mark"),
    );
    expect(
      contrast(
        parseHexColor(tokenHex(light, "--color-annotation-mark")),
        parseHexColor("#FFFFFF"),
      ),
      "annotation mark on white paper",
    ).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it("dark text is soft, not maximum-contrast", () => {
    const dark = readThemeTokens("dark");
    const ratio = contrast(
      color(dark, "--color-on-surface"),
      color(dark, "--color-surface"),
    );
    expect(ratio, "dark onSurface/surface contrast").toBeGreaterThanOrEqual(
      7.0,
    );
    expect(ratio).toBeLessThanOrEqual(13.0);
  });
});
