import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  APP_FONT_FAMILY,
  APP_TEXT_ROLES,
  type AppTextRoles,
} from "../src/renderer/theme/typography.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FONT_PATH = path.resolve(
  __dirname,
  "../../app/assets/fonts/NotoSansJP-VariableFont_wght.ttf",
);
const DESIGN_TOKENS_CSS_PATH = path.resolve(
  __dirname,
  "../src/renderer/styles/design-tokens.css",
);
const INDEX_CSS_PATH = path.resolve(
  __dirname,
  "../src/renderer/styles/index.css",
);

interface SfntTable {
  readonly offset: number;
  readonly length: number;
}

function parseSfntTables(bytes: Buffer): Map<string, SfntTable> {
  const tableCount = bytes.readUInt16BE(4);
  const tables = new Map<string, SfntTable>();
  for (let i = 0; i < tableCount; i++) {
    const recordOffset = 12 + i * 16;
    const tag = bytes.toString("ascii", recordOffset, recordOffset + 4);
    const offset = bytes.readUInt32BE(recordOffset + 8);
    const length = bytes.readUInt32BE(recordOffset + 12);
    tables.set(tag, { offset, length });
  }
  return tables;
}

interface FvarAxis {
  readonly tag: string;
  readonly min: number;
  readonly def: number;
  readonly max: number;
}

function parseFvarAxes(bytes: Buffer, fvarTable: SfntTable): FvarAxis[] {
  const axesOffset = bytes.readUInt16BE(fvarTable.offset + 4);
  const axisCount = bytes.readUInt16BE(fvarTable.offset + 8);
  const axisSize = bytes.readUInt16BE(fvarTable.offset + 10);
  const axes: FvarAxis[] = [];
  for (let i = 0; i < axisCount; i++) {
    const aOff = fvarTable.offset + axesOffset + i * axisSize;
    const tag = bytes.toString("ascii", aOff, aOff + 4);
    const min = bytes.readInt32BE(aOff + 4) / 65536;
    const def = bytes.readInt32BE(aOff + 8) / 65536;
    const max = bytes.readInt32BE(aOff + 12) / 65536;
    axes.push({ tag, min, def, max });
  }
  return axes;
}

describe("Typography & font invariants (INV-082 - INV-086)", () => {
  it("INV-082: the bundled file is still the whole variable font (fvar, >=17000 glyphs)", () => {
    expect(
      fs.existsSync(FONT_PATH),
      `Font file must exist at ${FONT_PATH}`,
    ).toBe(true);

    const bytes = fs.readFileSync(FONT_PATH);
    const tables = parseSfntTables(bytes);

    // 1. Must contain `fvar` table: confirms variable font (not swapped for static instance)
    expect(
      tables.has("fvar"),
      "no fvar table: this is a static instance, not the variable font",
    ).toBe(true);

    // 2. `maxp.numGlyphs` is uint16 at offset + 4: must have >= 17000 glyphs
    const maxp = tables.get("maxp");
    expect(maxp).toBeDefined();
    const numGlyphs = bytes.readUInt16BE(maxp!.offset + 4);
    expect(
      numGlyphs,
      `only ${numGlyphs} glyphs -- the font has been subset`,
    ).toBeGreaterThanOrEqual(17000);
  });

  it("INV-083: digits in score and numbers specify tabular-nums", () => {
    // 1. Role level: score role must specify tabular-nums
    expect(APP_TEXT_ROLES.score.fontVariantNumeric).toBe("tabular-nums");

    // 2. Design token level: CSS token must declare tabular-nums
    const designTokensCss = fs.readFileSync(DESIGN_TOKENS_CSS_PATH, "utf8");
    expect(designTokensCss).toMatch(
      /--font-variant-numeric-score:\s*tabular-nums;/,
    );

    // 3. Utility class level: .text-role-score must specify tabular-nums
    const indexCss = fs.readFileSync(INDEX_CSS_PATH, "utf8");
    expect(indexCss).toMatch(
      /\.text-role-score\s*\{[^}]*font-variant-numeric:\s*tabular-nums;/,
    );
  });

  it("INV-084: fontWeight drives the variable font axis (wght 100..900)", () => {
    const bytes = fs.readFileSync(FONT_PATH);
    const tables = parseSfntTables(bytes);
    const fvar = tables.get("fvar");
    expect(fvar).toBeDefined();

    const axes = parseFvarAxes(bytes, fvar!);
    const wghtAxis = axes.find((a) => a.tag === "wght");
    expect(wghtAxis).toBeDefined();
    expect(wghtAxis!.min).toBeLessThanOrEqual(100);
    expect(wghtAxis!.max).toBeGreaterThanOrEqual(900);

    // CSS @font-face declaration specifies the font-weight range 100 900 for Noto Sans JP
    const designTokensCss = fs.readFileSync(DESIGN_TOKENS_CSS_PATH, "utf8");
    expect(designTokensCss).toMatch(
      /@font-face\s*\{[^}]*font-family:\s*["']Noto Sans JP["'][^}]*font-weight:\s*100\s+900;[^}]*\}/s,
    );

    // All roles use font weights supported by the variable axis
    for (const [name, role] of Object.entries(APP_TEXT_ROLES)) {
      expect(
        role.fontWeight,
        `${name} fontWeight must fall within variable axis range [100, 900]`,
      ).toBeGreaterThanOrEqual(wghtAxis!.min);
      expect(
        role.fontWeight,
        `${name} fontWeight must fall within variable axis range [100, 900]`,
      ).toBeLessThanOrEqual(wghtAxis!.max);
    }
  });

  it("INV-085: every text role comes from the bundled family and has explicit line-height", () => {
    const roles = Object.keys(APP_TEXT_ROLES) as Array<keyof AppTextRoles>;
    expect(roles).toEqual([
      "questionText",
      "recognizedText",
      "gradingComment",
      "score",
      "uiLabel",
    ]);

    for (const roleName of roles) {
      const role = APP_TEXT_ROLES[roleName];
      expect(
        role.fontFamily,
        `${roleName} must specify bundled font family`,
      ).toBe(APP_FONT_FAMILY);
      expect(
        role.lineHeight,
        `${roleName} must specify explicit line-height for Japanese reading/UI`,
      ).toBeGreaterThan(0);
    }
  });

  it("INV-086: recognizedText is set apart from ordinary reading text (larger size and positive tracking)", () => {
    const recognized = APP_TEXT_ROLES.recognizedText;
    const bodyReading = APP_TEXT_ROLES.questionText;
    const grading = APP_TEXT_ROLES.gradingComment;

    const recognizedSize = parseFloat(recognized.fontSize);
    const bodySize = parseFloat(bodyReading.fontSize);
    expect(
      recognizedSize,
      "recognizedText font-size must be larger than body reading font-size",
    ).toBeGreaterThan(bodySize);

    const recognizedTracking = parseFloat(String(recognized.letterSpacing));
    expect(
      recognizedTracking,
      "recognizedText must carry positive letter-spacing (tracking) for character comparison",
    ).toBeGreaterThan(0);

    const gradingTracking = parseFloat(String(grading.letterSpacing));
    expect(
      gradingTracking,
      "gradingComment must have zero tracking so Latin tracking does not open gaps in Japanese words",
    ).toBe(0);
  });
});
