import { readFileSync, readdirSync } from "node:fs";
import * as path from "node:path";

import { describe, expect, it } from "vitest";

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
 * Issue #381: `<select>` must match the app theme, including the opened list.
 *
 * The whole look lives in one `@layer components` rule set in `index.css`;
 * features only add the `select-themed` class. These tests pin the structure
 * that makes `appearance: base-select` reach the popup (`::picker(select)`,
 * `::picker-icon`) and the coverage of every `<select>` under `features/`, plus
 * the AA contrast of the token roles the rules resolve to.
 */

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const INDEX_CSS = path.join(PACKAGE_ROOT, "src/renderer/styles/index.css");
const FEATURES_DIR = path.join(PACKAGE_ROOT, "src/renderer/features");

const THEMES = ["light", "dark"] as const satisfies readonly ThemeName[];

function css(): string {
  return readFileSync(INDEX_CSS, "utf8");
}

/** Body of the first rule whose selector is exactly `selector`. */
function ruleBlock(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`${escaped}\\s*\\{([^}]*)\\}`).exec(css());
  expect(match, `${selector} の規則が index.css に無い`).not.toBeNull();
  return match![1]!;
}

function walkTsx(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkTsx(full));
    } else if (full.endsWith(".tsx")) {
      files.push(full);
    }
  }
  return files;
}

interface SelectTag {
  readonly file: string;
  readonly tag: string;
}

/**
 * Scans a JSX opening tag from `<select` to its closing `>`, tracking quotes
 * and `{}` depth so the `=>` inside an `onChange` handler does not end the tag
 * early.
 */
function readOpeningTag(source: string, start: number): string {
  let depth = 0;
  let quote: string | null = null;
  let index = start;
  for (; index < source.length; index += 1) {
    const char = source[index]!;
    if (quote !== null) {
      if (char === "\\") {
        index += 1;
      } else if (char === quote) {
        quote = null;
      }
      continue;
    }
    if (char === '"' || char === "'" || char === "`") {
      quote = char;
    } else if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
    } else if (char === ">" && depth === 0) {
      break;
    }
  }
  return source.slice(start, index + 1);
}

function findSelectTags(): SelectTag[] {
  const tags: SelectTag[] = [];
  for (const file of walkTsx(FEATURES_DIR).sort()) {
    const source = readFileSync(file, "utf8");
    const relative = path
      .relative(PACKAGE_ROOT, file)
      .split(path.sep)
      .join("/");
    let cursor = 0;
    while (cursor < source.length) {
      const start = source.indexOf("<select", cursor);
      if (start === -1) {
        break;
      }
      const next = source[start + "<select".length];
      if (next !== undefined && /[A-Za-z0-9_-]/.test(next)) {
        cursor = start + "<select".length;
        continue;
      }
      const tag = readOpeningTag(source, start);
      tags.push({ file: relative, tag });
      cursor = start + tag.length;
    }
  }
  return tags;
}

function color(tokens: Map<string, string>, name: `--${string}`) {
  return parseHexColor(tokenHex(tokens, name));
}

describe("select theming (Issue #381)", () => {
  it("styles the closed control with `appearance: base-select`", () => {
    const block = ruleBlock(".select-themed");
    expect(block).toMatch(/appearance:\s*base-select/);
    expect(block).toContain("color: var(--color-on-surface)");
    expect(block).toContain(
      "background-color: var(--color-surface-container-high)",
    );
  });

  it("draws the opened list as a page picker, not the OS list", () => {
    const block = ruleBlock(".select-themed::picker(select)");
    expect(block).toMatch(/appearance:\s*base-select/);
    expect(block).toContain(
      "background-color: var(--color-surface-container-high)",
    );
    expect(block).toContain("color: var(--color-on-surface)");
    expect(block).toContain("border: var(--layout-hairline)");
    expect(block).toContain("box-shadow: var(--elevation-modal)");
  });

  it("colours the picker arrow from a token", () => {
    const block = ruleBlock(".select-themed::picker-icon");
    expect(block).toContain("color: var(--color-on-surface-variant)");
  });

  it("marks every state with tokens, and the selected one without colour alone", () => {
    expect(ruleBlock(".select-themed:hover:not(:disabled)")).toContain(
      "background-color: var(--color-surface-container-highest)",
    );

    const checked = ruleBlock(".select-themed option:checked");
    expect(checked).toContain("color: var(--color-on-primary-container)");
    expect(checked).toContain(
      "background-color: var(--color-primary-container)",
    );
    expect(checked).toMatch(/font-weight:\s*600/);
    expect(ruleBlock(".select-themed option:checked::checkmark")).toContain(
      "var(--color-primary-text)",
    );

    const disabled = ruleBlock(".select-themed:disabled");
    expect(disabled).toContain("color: var(--color-disabled-button-label)");
    expect(disabled).toContain(
      "background-color: var(--color-disabled-button-container)",
    );
    expect(disabled).toContain(
      "border-color: var(--color-disabled-button-outline)",
    );
  });

  it("keeps a keyboard focus ring on the primary token", () => {
    const block = ruleBlock(".select-themed:focus-visible");
    expect(block).toMatch(/outline:/);
    expect(block).toContain("var(--color-primary)");
  });

  it("adds `select-themed` to every <select> under features/ (no misses)", () => {
    const tags = findSelectTags();
    const missing = tags.filter(
      (entry) => !entry.tag.includes("select-themed"),
    );

    expect(
      missing.map((entry) => `${entry.file}: ${entry.tag}`),
      "select-themed の付いていない <select> がある",
    ).toEqual([]);

    const byFile = new Map<string, number>();
    for (const entry of tags) {
      byFile.set(entry.file, (byFile.get(entry.file) ?? 0) + 1);
    }
    expect(Object.fromEntries(byFile)).toEqual({
      "src/renderer/features/answer-area-editor/AnswerAreaEditor.tsx": 2,
      "src/renderer/features/intake/IntakePage.tsx": 3,
      "src/renderer/features/settings/IntakeTemplateTab.tsx": 4,
    });
  });
});

describe("select token contrast (Issue #381)", () => {
  for (const theme of THEMES) {
    const tokens = readThemeTokens(theme);

    it(`${theme}: text roles meet AA on the select surfaces`, () => {
      expect(
        contrast(
          color(tokens, "--color-on-surface"),
          color(tokens, "--color-surface-container-high"),
        ),
        "onSurface on surfaceContainerHigh (closed control / picker / option)",
      ).toBeGreaterThanOrEqual(AA_TEXT);
      expect(
        contrast(
          color(tokens, "--color-on-surface"),
          color(tokens, "--color-surface-container-highest"),
        ),
        "onSurface on surfaceContainerHighest (hover)",
      ).toBeGreaterThanOrEqual(AA_TEXT);
      expect(
        contrast(
          color(tokens, "--color-on-primary-container"),
          color(tokens, "--color-primary-container"),
        ),
        "onPrimaryContainer on primaryContainer (checked option)",
      ).toBeGreaterThanOrEqual(AA_TEXT);
      expect(
        contrast(
          color(tokens, "--color-disabled-button-label"),
          color(tokens, "--color-disabled-button-container"),
        ),
        "disabled label on its container",
      ).toBeGreaterThanOrEqual(AA_TEXT);
    });

    it(`${theme}: the picker arrow is findable on its surface`, () => {
      expect(
        contrast(
          color(tokens, "--color-on-surface-variant"),
          color(tokens, "--color-surface-container-high"),
        ),
        "onSurfaceVariant on surfaceContainerHigh",
      ).toBeGreaterThanOrEqual(AA_NON_TEXT);
    });
  }
});
