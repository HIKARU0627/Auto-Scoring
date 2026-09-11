import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FEATURES_DIR = path.resolve(__dirname, "../src/renderer/features");

/**
 * INV-080: Static analysis lint test prohibiting raw style and color literals
 * in `desktop/src/renderer/features/`.
 *
 * Enforces design token usage (spacing, radius, colors, typography, layout)
 * following Commander's strict allowlist policy:
 * 1. Scope and exemptions defined and documented in `docs/design-tokens.md`.
 * 2. Pre-existing violations strictly tracked by identity (file, symbol, literal, line).
 * 3. Allowlist count is capped at EXPECTED_ALLOWLIST_COUNT; entries can only decrease.
 * 4. File scan count is asserted (>= EXPECTED_MIN_FILES) to prevent false-green glob misses.
 * 5. Removal issue attached to each entry; until the commander files it, the
 *    placeholder `TODO(owner)` marks it as pending (no invented issue numbers).
 */

export const EXPECTED_MIN_FILES = 24;
export const EXPECTED_ALLOWLIST_COUNT = 27;

export interface AllowlistEntry {
  readonly file: string;
  readonly symbol: string;
  readonly rule: string;
  readonly literal: string;
  readonly line: number;
  /**
   * Issue tracking the removal of this violation. Until the commander files
   * it, this is the placeholder `TODO(owner)` rather than an invented number.
   */
  readonly removalIssue: string;
}

/**
 * Strict allowlist of existing violations in `desktop/src/renderer/features/`.
 * Each entry is tagged with its removal issue.
 */
export const ALLOWLIST: readonly AllowlistEntry[] = [
  // answer-area-editor: カスタムハンドルと枠線のリテラル
  {
    file: "src/renderer/features/answer-area-editor/AnswerAreaEditor.tsx",
    symbol: "RegionOverlay",
    rule: "arbitrary-bracket",
    literal: "border-[3px]",
    line: 704,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/answer-area-editor/AnswerAreaEditor.tsx",
    symbol: "RegionOverlay",
    rule: "arbitrary-bracket",
    literal: "border-[1.5px]",
    line: 704,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/answer-area-editor/AnswerAreaEditor.tsx",
    symbol: "RegionOverlay",
    rule: "arbitrary-bracket",
    literal: "h-[14px]",
    line: 743,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/answer-area-editor/AnswerAreaEditor.tsx",
    symbol: "RegionOverlay",
    rule: "arbitrary-bracket",
    literal: "w-[14px]",
    line: 743,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },

  // home: ダッシュボード最大幅のリテラル
  {
    file: "src/renderer/features/home/HomePage.tsx",
    symbol: "HomePage",
    rule: "arbitrary-bracket",
    literal: "max-w-[960px]",
    line: 91,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },

  // intake: ページレイアウト幅制約のリテラル
  {
    file: "src/renderer/features/intake/IntakePage.tsx",
    symbol: "IntakePage",
    rule: "arbitrary-bracket",
    literal: "max-w-[720px]",
    line: 399,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },

  // pdf-review: インスペクター最大高さ制約のリテラル
  {
    file: "src/renderer/features/pdf-review/PdfReviewPage.tsx",
    symbol: "PdfReviewPage",
    rule: "arbitrary-bracket",
    literal: "max-h-[80vh]",
    line: 531,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },

  // review-queue: ダイアログバックドロップの背景色リテラル (bg-black/50)
  {
    file: "src/renderer/features/review-queue/BulkExportDialog.tsx",
    symbol: "BulkExportDialog",
    rule: "non-token-color",
    literal: "bg-black/50",
    line: 127,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/review-queue/ExportDialog.tsx",
    symbol: "ExportDialog",
    rule: "non-token-color",
    literal: "bg-black/50",
    line: 255,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },

  // submission-queue: テーブルおよびチップのスタイルリテラル
  {
    file: "src/renderer/features/review-queue/SubmissionQueuePage.tsx",
    symbol: "SubmissionQueuePage",
    rule: "arbitrary-bracket",
    literal: "max-w-[960px]",
    line: 140,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/review-queue/SubmissionQueuePage.tsx",
    symbol: "SubmissionQueuePage",
    rule: "numeric-spacing",
    literal: "py-0.5",
    line: 214,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/review-queue/SubmissionQueuePage.tsx",
    symbol: "SubmissionQueuePage",
    rule: "bare-rounded",
    literal: "rounded",
    line: 214,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/review-queue/SubmissionQueuePage.tsx",
    symbol: "SubmissionQueuePage",
    rule: "bare-rounded",
    literal: "rounded",
    line: 253,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },

  // settings: APIキー設定タブのドット間隔リテラル
  {
    file: "src/renderer/features/settings/ApiKeyTab.tsx",
    symbol: "ApiKeyTab",
    rule: "numeric-spacing",
    literal: "mt-1.5",
    line: 387,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },

  // settings: 取込テンプレートタブのテーブルスタイルリテラル
  {
    file: "src/renderer/features/settings/IntakeTemplateTab.tsx",
    symbol: "IntakeTemplateTab",
    rule: "numeric-spacing",
    literal: "mt-1",
    line: 267,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/settings/IntakeTemplateTab.tsx",
    symbol: "IntakeTemplateTab",
    rule: "bare-rounded",
    literal: "rounded",
    line: 267,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/settings/IntakeTemplateTab.tsx",
    symbol: "IntakeTemplateTab",
    rule: "bare-rounded",
    literal: "rounded",
    line: 322,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/settings/IntakeTemplateTab.tsx",
    symbol: "IntakeTemplateTab",
    rule: "arbitrary-bracket",
    literal: "min-w-[120px]",
    line: 339,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/settings/IntakeTemplateTab.tsx",
    symbol: "IntakeTemplateTab",
    rule: "bare-rounded",
    literal: "rounded",
    line: 339,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/settings/IntakeTemplateTab.tsx",
    symbol: "IntakeTemplateTab",
    rule: "bare-rounded",
    literal: "rounded",
    line: 352,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/settings/IntakeTemplateTab.tsx",
    symbol: "IntakeTemplateTab",
    rule: "bare-rounded",
    literal: "rounded",
    line: 371,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/settings/IntakeTemplateTab.tsx",
    symbol: "IntakeTemplateTab",
    rule: "bare-rounded",
    literal: "rounded",
    line: 383,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },

  // startup: 起動オーバーレイのエラーアイコンサイズと幅制約リテラル
  {
    file: "src/renderer/features/startup/SidecarStartupOverlay.tsx",
    symbol: "SidecarErrorScreen",
    rule: "arbitrary-bracket",
    literal: "max-w-[560px]",
    line: 72,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/startup/SidecarStartupOverlay.tsx",
    symbol: "SidecarErrorScreen",
    rule: "arbitrary-bracket",
    literal: "text-[48px]",
    line: 75,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },

  // submission-confirm: 答案確定画面の最大幅と切り抜き高さリテラル
  {
    file: "src/renderer/features/submission-confirm/SubmissionConfirmPage.tsx",
    symbol: "SubmissionConfirmPage",
    rule: "arbitrary-bracket",
    literal: "max-w-[960px]",
    line: 531,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/submission-confirm/SubmissionConfirmPage.tsx",
    symbol: "SubmissionConfirmPage",
    rule: "arbitrary-bracket",
    literal: "h-[180px]",
    line: 590,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
  {
    file: "src/renderer/features/submission-confirm/SubmissionConfirmPage.tsx",
    symbol: "SubmissionConfirmPage",
    rule: "arbitrary-bracket",
    literal: "max-w-[960px]",
    line: 681,
    removalIssue: "TODO(owner): 撤去先 Issue は司令塔が起票予定",
  },
];

function walkFiles(dir: string): string[] {
  const result: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      result.push(...walkFiles(full));
    } else if (full.endsWith(".ts") || full.endsWith(".tsx")) {
      result.push(full);
    }
  }
  return result;
}

function findEnclosingComponent(lines: string[], idx: number): string {
  for (let i = idx; i >= 0; i--) {
    const line = lines[i]!;
    const fnMatch = /^(?:export\s+)?function\s+([A-Za-z0-9_]+)/.exec(line);
    if (fnMatch) return fnMatch[1]!;
    const constMatch =
      /^(?:export\s+)?const\s+([A-Za-z0-9_]+)\s*[:=]\s*(?:\([^)]*\)|[A-Za-z0-9_]+)\s*=>/.exec(
        line,
      );
    if (constMatch) return constMatch[1]!;
  }
  return "module";
}

interface FoundViolation {
  readonly file: string;
  readonly symbol: string;
  readonly rule: string;
  readonly literal: string;
  readonly line: number;
  readonly snippet: string;
}

const RE_NON_TOKEN_COLOR =
  /\b(?:bg|text|border|fill|stroke)-(?:black|white)(?:\/[0-9]+)?\b/g;
const RE_HEX_COLOR = /#[0-9a-fA-F]{3,8}\b/g;
const RE_ARBITRARY_BRACKET = /\b[\w-]+-\[[^\]]+\]/g;
const RE_NUMERIC_SPACING =
  /\b(?:p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|gap)-[0-9]+(?:\.[0-9]+)?\b/g;
const RE_BARE_ROUNDED = /(?<=[\s"`'])rounded(?=[\s"`']|$)/g;

/**
 * 違反の同一性キー。`line` まで含めるのは、同じファイル・同じシンボルにある
 * 同種リテラルでも、別の行の違反を別エントリとして厳密に区別するためである。
 */
function violationKey(v: {
  file: string;
  symbol: string;
  rule: string;
  literal: string;
  line: number;
}): string {
  return `${v.file}::${v.symbol}::${v.rule}::${v.literal}::${v.line}`;
}

/**
 * 1 ファイル分のソースから違反を抽出する。走査器そのものを fixture で
 * 正の対照検査できるよう、ファイル読み込みから分離している。
 */
function findViolationsInSource(
  relativeFile: string,
  content: string,
): FoundViolation[] {
  const violations: FoundViolation[] = [];
  const lines = content.split("\n");

  for (let idx = 0; idx < lines.length; idx++) {
    const line = lines[idx]!.trim();
    if (
      line.startsWith("//") ||
      line.startsWith("*") ||
      line.startsWith("/*")
    ) {
      continue;
    }

    const symbol = findEnclosingComponent(lines, idx);
    const lineNum = idx + 1;

    for (const m of line.matchAll(RE_NON_TOKEN_COLOR)) {
      violations.push({
        file: relativeFile,
        symbol,
        rule: "non-token-color",
        literal: m[0],
        line: lineNum,
        snippet: line,
      });
    }

    for (const m of line.matchAll(RE_HEX_COLOR)) {
      violations.push({
        file: relativeFile,
        symbol,
        rule: "hex-color",
        literal: m[0],
        line: lineNum,
        snippet: line,
      });
    }

    for (const m of line.matchAll(RE_ARBITRARY_BRACKET)) {
      violations.push({
        file: relativeFile,
        symbol,
        rule: "arbitrary-bracket",
        literal: m[0],
        line: lineNum,
        snippet: line,
      });
    }

    for (const m of line.matchAll(RE_NUMERIC_SPACING)) {
      violations.push({
        file: relativeFile,
        symbol,
        rule: "numeric-spacing",
        literal: m[0],
        line: lineNum,
        snippet: line,
      });
    }

    if (line.includes("className") || line.includes("rounded")) {
      for (const m of line.matchAll(RE_BARE_ROUNDED)) {
        if (!/rounded-(?:sm|md|lg|full|none)/.test(line)) {
          violations.push({
            file: relativeFile,
            symbol,
            rule: "bare-rounded",
            literal: m[0],
            line: lineNum,
            snippet: line,
          });
        }
      }
    }
  }

  return violations;
}

/**
 * パス区切りを `/` に正規化する。Windows の `path.relative` は区切りに `\` を
 * 返すが、allowlist は `/` で書かれている。正規化しないと Windows CI だけ
 * 全エントリが不一致になる（PR #282 で発生した赤の原因）。
 */
function toPosixPath(relativePath: string): string {
  return relativePath.split(/[\\/]/).join("/");
}

function scanFeatures(): {
  files: string[];
  violations: FoundViolation[];
} {
  const desktopRoot = path.resolve(__dirname, "..");
  const files = walkFiles(FEATURES_DIR).sort();
  const violations: FoundViolation[] = [];

  for (const fpath of files) {
    const rel = toPosixPath(path.relative(desktopRoot, fpath));
    violations.push(
      ...findViolationsInSource(rel, fs.readFileSync(fpath, "utf8")),
    );
  }

  return { files, violations };
}

describe("Design tokens static lint test under src/renderer/features (INV-080)", () => {
  it("scans at least the expected number of features files (prevents glob miss)", () => {
    const { files } = scanFeatures();
    expect(
      files.length,
      `Expected >= ${EXPECTED_MIN_FILES} features files to be scanned, found ${files.length}`,
    ).toBeGreaterThanOrEqual(EXPECTED_MIN_FILES);
  });

  it("normalizes Windows path separators to POSIX before matching the allowlist", () => {
    // Windows CI だけ全エントリが不一致になった回帰の再発防止。
    expect(toPosixPath("src\\renderer\\features\\home\\HomePage.tsx")).toBe(
      "src/renderer/features/home/HomePage.tsx",
    );
    expect(toPosixPath("src/renderer/features/home/HomePage.tsx")).toBe(
      "src/renderer/features/home/HomePage.tsx",
    );
  });

  it("allowlist count does not increase beyond the baseline cap", () => {
    expect(
      ALLOWLIST.length,
      `Allowlist count cannot increase beyond ${EXPECTED_ALLOWLIST_COUNT}. Current: ${ALLOWLIST.length}`,
    ).toBeLessThanOrEqual(EXPECTED_ALLOWLIST_COUNT);
  });

  it("scanner detects violations and ignores token-based styles (positive control)", () => {
    // 走査器そのものの正の対照。実ツリーから違反が消えても、この検査が
    // 通らなければ走査が空振りしていると分かる。違反はそれぞれ別行に置き、
    // 行単位の `rounded-md` 抑止が他の検出を巻き込まないようにする。
    const fixture = [
      "export function Widget() {",
      '  return <div className="mt-1 rounded max-w-[960px] bg-black/50" style={{ color: "#fff" }} />;',
      "}",
      "export function Clean() {",
      '  return <div className="p-md gap-lg rounded-md bg-surface text-on-surface" />;',
      "}",
    ].join("\n");

    const found = findViolationsInSource("fixture.tsx", fixture);
    const rules = new Set(found.map((v) => `${v.rule}:${v.literal}`));
    expect(rules).toContain("numeric-spacing:mt-1");
    expect(rules).toContain("bare-rounded:rounded");
    expect(rules).toContain("arbitrary-bracket:max-w-[960px]");
    expect(rules).toContain("non-token-color:bg-black/50");
    expect(rules).toContain("hex-color:#fff");
    // トークン由来のスタイル（`p-md`, `gap-lg`, `rounded-md`, `bg-surface`,
    // `text-on-surface`）は拾わない。
    expect(found.filter((v) => v.symbol === "Clean")).toEqual([]);
  });

  it("all violations in features/ are strictly permitted in the allowlist", () => {
    const { violations } = scanFeatures();

    const allowlistKeys = new Set(ALLOWLIST.map(violationKey));

    const unpermitted: FoundViolation[] = [];
    for (const v of violations) {
      if (!allowlistKeys.has(violationKey(v))) {
        unpermitted.push(v);
      }
    }

    if (unpermitted.length > 0) {
      const formatted = unpermitted
        .map(
          (u) =>
            `  ${u.file}:${u.line} [${u.symbol}] ${u.rule}: ${u.literal}\n    snippet: ${u.snippet}`,
        )
        .join("\n");
      expect.fail(
        `Found ${unpermitted.length} unpermitted design-token violation(s) in features/:\n${formatted}\n` +
          "Do not hardcode styles/colors in features/. Use design tokens, or if legacy, register in allowlist with issue link.",
      );
    }
  });
});
