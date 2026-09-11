import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, type Dirent } from "node:fs";
import * as path from "node:path";

import {
  AA_NON_TEXT,
  alphaBlend,
  contrast,
  parseHexColor,
} from "../src/shared/contrast";
import { APP_TEXT_ROLES } from "../src/renderer/theme/typography.js";
import {
  readThemeTokens,
  tokenHex,
  type ThemeName,
} from "./support/read-design-tokens";

/**
 * Design-token / accessibility invariants carried over from the Flutter app
 * (`docs/frontend-invariants.md` §6, rows INV-091 / INV-092 / INV-095;
 * Issue #322).
 *
 * Flutter resolved these through `ThemeExtension` objects that a widget could
 * null-dereference (`context.statusColors!`). The Electron renderer resolves
 * them through `styles/design-tokens.css` plus the Tailwind bridge in
 * `styles/index.css`, so the crash shape no longer exists. These tests pin that
 * structure: every promise is backed by a token that must be present in both
 * themes and bridged into a utility, and the old crash surface is absent.
 *
 * The scanners carry a positive-control fixture so a renamed file or a broken
 * regex cannot leave them passing vacuously.
 */

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const RENDERER_DIR = path.join(PACKAGE_ROOT, "src/renderer");
const BRIDGE_PATH = path.join(PACKAGE_ROOT, "src/renderer/styles/index.css");
const THEMES = ["light", "dark"] as const satisfies readonly ThemeName[];

/** INV-092: one disabled value per button variant, resolved from a token. */
const DISABLED_BUTTON_TOKENS = [
  "--color-disabled-button-outline",
  "--color-disabled-button-label",
  "--color-disabled-button-container",
] as const;

/** INV-095: the status colour family the UI reads by name. */
const STATUS_TOKENS = [
  "--color-attention",
  "--color-attention-container",
  "--color-on-attention-container",
  "--color-success",
  "--color-success-container",
  "--color-on-success-container",
  "--color-error",
  "--color-error-container",
  "--color-on-error-container",
] as const;

/**
 * INV-095: every typed text role must be materialised as a Tailwind utility.
 * The names are written out rather than derived because the mapping
 * (`recognizedText` -> `text-role-recognized`) is not mechanical.
 */
const ROLE_UTILITY: Readonly<Record<keyof typeof APP_TEXT_ROLES, string>> = {
  questionText: "text-role-question",
  recognizedText: "text-role-recognized",
  gradingComment: "text-role-grading-comment",
  score: "text-role-score",
  uiLabel: "text-role-ui-label",
};

function rendererSourceFiles(): string[] {
  const found: string[] = [];
  let entries: Dirent[];
  try {
    entries = readdirSync(RENDERER_DIR, {
      withFileTypes: true,
      recursive: true,
    });
  } catch {
    return [];
  }
  for (const entry of entries) {
    if (
      !entry.isFile() ||
      !new Set([".ts", ".tsx"]).has(path.extname(entry.name))
    ) {
      continue;
    }
    found.push(path.join(entry.parentPath, entry.name));
  }
  return found.sort();
}

/** The Flutter `ThemeExtension` crash surface, if any source reintroduces it. */
const THEME_EXTENSION_CRASH = /\bThemeExtension\b|\bstatusColors\b/g;

function detectThemeExtensionCrash(source: string): string[] {
  return [...source.matchAll(THEME_EXTENSION_CRASH)].map((match) => match[0]);
}

function expectBridged(bridge: string, token: string): void {
  expect(
    bridge,
    `${token} が index.css の @theme inline にブリッジされていない`,
  ).toMatch(new RegExp(`${token}:\\s*var\\(${token}\\)`));
}

describe("disabled button colours resolve from tokens (INV-092)", () => {
  it("every disabled-button token is defined in light and dark", () => {
    for (const theme of THEMES) {
      const tokens = readThemeTokens(theme);
      for (const token of DISABLED_BUTTON_TOKENS) {
        expect(
          tokenHex(tokens, token).length,
          `${theme}: ${token} が空`,
        ).toBeGreaterThan(0);
      }
    }
  });

  it("every disabled-button token is bridged into Tailwind", () => {
    const bridge = readFileSync(BRIDGE_PATH, "utf8");
    for (const token of DISABLED_BUTTON_TOKENS) {
      expectBridged(bridge, token);
    }
  });
});

describe("status colours and text roles are registered (INV-095)", () => {
  it("every status colour token is defined in light and dark", () => {
    for (const theme of THEMES) {
      const tokens = readThemeTokens(theme);
      for (const token of STATUS_TOKENS) {
        expect(
          tokenHex(tokens, token).length,
          `${theme}: ${token} が空`,
        ).toBeGreaterThan(0);
      }
    }
  });

  it("every status colour token is bridged into Tailwind", () => {
    const bridge = readFileSync(BRIDGE_PATH, "utf8");
    for (const token of STATUS_TOKENS) {
      expectBridged(bridge, token);
    }
  });

  it("every typed text role has a matching utility class", () => {
    // A role added to the typed source without a utility would be an
    // unregistered extension: the compiler sees the role, the browser does not.
    expect(Object.keys(ROLE_UTILITY).sort()).toEqual(
      Object.keys(APP_TEXT_ROLES).sort(),
    );
    const bridge = readFileSync(BRIDGE_PATH, "utf8");
    for (const [role, utility] of Object.entries(ROLE_UTILITY)) {
      expect(bridge, `${role} -> .${utility} が無い`).toMatch(
        new RegExp(`\\.${utility}\\s*\\{`),
      );
    }
  });

  it("the Flutter ThemeExtension null-dereference surface is absent", () => {
    // Positive control: the scanner actually recognises the crash shape.
    expect(
      detectThemeExtensionCrash("const c = context.statusColors!;"),
    ).toEqual(["statusColors"]);
    expect(
      detectThemeExtensionCrash("class X extends ThemeExtension<X> {}"),
    ).toEqual(["ThemeExtension"]);

    const violations = rendererSourceFiles().flatMap((file) => {
      const source = readFileSync(file, "utf8");
      return detectThemeExtensionCrash(source).map(
        (hit) => `${path.relative(PACKAGE_ROOT, file)}: ${hit}`,
      );
    });
    expect(
      violations,
      "Flutter の ThemeExtension / context.statusColors が再導入されている",
    ).toEqual([]);
  });
});

describe("Material's default disabled outline stays a measured shortfall (INV-091)", () => {
  it("the default is below AA non-text, and the override token clears it", () => {
    for (const theme of THEMES) {
      const tokens = readThemeTokens(theme);
      const onSurface = parseHexColor(tokenHex(tokens, "--color-on-surface"));
      const surface = parseHexColor(
        tokenHex(tokens, "--color-surface-container-low"),
      );
      const materialDefault = alphaBlend(onSurface, 0.12, surface);
      expect(
        contrast(materialDefault, surface),
        `${theme}: Material 既定の disabled outline`,
      ).toBeLessThan(AA_NON_TEXT);

      const override = parseHexColor(
        tokenHex(tokens, "--color-disabled-button-outline"),
      );
      expect(
        contrast(override, surface),
        `${theme}: 上書き後の disabled outline`,
      ).toBeGreaterThanOrEqual(AA_NON_TEXT);
    }
  });
});
