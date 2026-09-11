import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, type Dirent } from "node:fs";
import * as path from "node:path";

import {
  ActionRequirements,
  type ActionRequirement,
} from "../src/renderer/core/action-requirements.js";

/**
 * INV-004 / INV-101: 無効理由の単一ソース性と文言規約 (Issue #271).
 *
 * このファイルが固定するのは 2 つの約束である。
 *
 * - INV-004: 「その操作がいま使えない理由」を説明する文言は
 *   `core/action-requirements.ts` の単一ソースから出す。画面 (`features/`) が
 *   `message` / `action` の prop へ独自の理由文を直書きしたら赤くなる。
 * - INV-101: `ActionRequirements` の全メンバーの理由文が「。」で終わり、例外名や
 *   HTTP ステータスコード等の内部診断文を含まない。メンバーを列挙して回るので、
 *   新しい理由を足した人が規約を破っても赤くなる。
 *
 * 否定形アサーションが空振りしないよう、走査したファイル数と、走査器そのものの
 * 正の対照 (fixture) も同じファイルで固定する。
 */

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const FEATURES_DIR = path.join(PACKAGE_ROOT, "src/renderer/features");
const SOURCE_EXTENSIONS = new Set([".ts", ".tsx"]);

/**
 * 対象範囲は `docs/frontend-invariants.md` §7.1 に定義する。
 *
 * 「操作がいま使えない理由」を説明する文言だけを対象にする。画面が理由を出す
 * ときの通り道は `message` / `action` の prop である。フォーム入力の
 * バリデーション (`setError(...)`) は項目単位の入力エラーであって操作の無効理由
 * ではなく、起動オーバーレイ・接続状態の説明は UG 系の担当なので、いずれも
 * この走査には現れない。
 */
const REASON_PROPS = new Set(["message", "action"]);

interface DetectedReason {
  /** `desktop/` からの相対パス。 */
  readonly file: string;
  /** 1 始まりの行番号。 */
  readonly line: number;
  /** `message` か `action`。 */
  readonly prop: string;
  /** 空白を正規化し、補間を `${…}` に潰した理由文。 */
  readonly message: string;
}

/**
 * Issue #271 が #255 との衝突を避けるために残した既存の違反リスト。Issue #278 で
 * `BlockerNotice` の message 6 件と `AnswerAreaEditor.MissingGroup` の message 2 件 /
 * action 2 件を `core/action-requirements.ts` へ移したため、いまは空である。
 *
 * 実物を数えると 10 件だった（Issue #278 の本文は 9 件と書いているが、allowlist
 * の実物は BlockerNotice 6 + MissingGroup message 2 / action 2 の 10 件である）。
 * 以後は同じファイルに新しい違反を足しても (下の「許容済み」検査に無い) 赤くなる。
 */
const OUTSTANDING_REASONS: readonly {
  readonly file: string;
  readonly component: string;
  readonly message: string;
}[] = [];

/** この数は allowlist を増やしたら赤くなるための固定値である。 */
const OUTSTANDING_REASON_COUNT = 0;

/**
 * 走査対象が 0 件になったら赤くするための下限。`design-tokens-lint.test.ts` の
 * `EXPECTED_MIN_FILES` と同じ役割で、否定形アサーションが空振りするのを防ぐ。
 */
const EXPECTED_MIN_FEATURE_FILES = 24;

function featureFiles(): string[] {
  const found: string[] = [];
  let entries: Dirent[];
  try {
    entries = readdirSync(FEATURES_DIR, {
      withFileTypes: true,
      recursive: true,
    });
  } catch {
    // 走査ディレクトリが無いときは空を返し、件数の下限検査で赤くする。
    // ここで例外を投げると「赤」ではあるが、件数アサーションの失敗ではなくなる。
    return [];
  }
  for (const entry of entries) {
    if (!entry.isFile() || !SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      continue;
    }
    found.push(
      path
        .relative(PACKAGE_ROOT, path.join(entry.parentPath, entry.name))
        .split(path.sep)
        .join("/"),
    );
  }
  return found.sort();
}

function normalize(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/** 文字列リテラルを読み飛ばし、閉じ引用符の次を返す。 */
function skipString(source: string, start: number, quote: string): number {
  let index = start + 1;
  while (index < source.length && source[index] !== quote) {
    index += source[index] === "\\" ? 2 : 1;
  }
  return Math.min(index + 1, source.length);
}

/**
 * テンプレートリテラルを読み、補間の中身を `${…}` に潰した本文を返す。
 * 補間の中は入れ子のテンプレート・文字列・波括弧を数えて読み飛ばす。
 */
function readTemplate(
  source: string,
  backtick: number,
): { text: string; end: number } {
  let index = backtick + 1;
  let text = "";
  while (index < source.length) {
    const char = source[index];
    if (char === "\\") {
      text += source[index] + (source[index + 1] ?? "");
      index += 2;
      continue;
    }
    if (char === "`") {
      return { text, end: index + 1 };
    }
    if (char === "$" && source[index + 1] === "{") {
      text += "${…}";
      index = skipInterpolation(source, index + 2);
      continue;
    }
    text += char;
    index += 1;
  }
  return { text, end: source.length };
}

function skipInterpolation(source: string, start: number): number {
  let index = start;
  let depth = 1;
  while (index < source.length && depth > 0) {
    const char = source[index];
    if (char === "\\") {
      index += 2;
      continue;
    }
    if (char === "`") {
      index = readTemplate(source, index).end;
      continue;
    }
    if (char === '"' || char === "'") {
      index = skipString(source, index, char);
      continue;
    }
    if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
    }
    index += 1;
  }
  return index;
}

function lineOf(source: string, index: number): number {
  return source.slice(0, index).split("\n").length;
}

/**
 * `features/` のソースから、`message` / `action` に直書きされた「。」終わりの
 * 文字列リテラルを拾う。
 *
 * 直接の文字列・テンプレートだけを見る。三項演算子や関数呼び出しの値
 * (`message={ outcome ? "..." : "..." }` のような操作結果の通知) は理由文の
 * 直書きではないので対象外である。属性は Prettier により `name=value` の形に
 * 揃うので、`message =` という代入と取り違えない。
 */
function detectReasons(relativeFile: string, source: string): DetectedReason[] {
  const found: DetectedReason[] = [];
  let index = 0;

  while (index < source.length) {
    const char = source[index] ?? "";
    const next = source[index + 1] ?? "";

    if (char === "/" && next === "/") {
      while (index < source.length && source[index] !== "\n") {
        index += 1;
      }
      continue;
    }
    if (char === "/" && next === "*") {
      index += 2;
      while (
        index < source.length &&
        !(source[index] === "*" && source[index + 1] === "/")
      ) {
        index += 1;
      }
      index += 2;
      continue;
    }
    if (char === '"' || char === "'") {
      index = skipString(source, index, char);
      continue;
    }
    if (char === "`") {
      index = readTemplate(source, index).end;
      continue;
    }

    if (/[A-Za-z_$]/.test(char) && !/[\w$-]/.test(source[index - 1] ?? "")) {
      let end = index;
      while (end < source.length && /[\w$-]/.test(source[end] ?? "")) {
        end += 1;
      }
      const word = source.slice(index, end);
      let cursor = end;
      while (cursor < source.length && /\s/.test(source[cursor] ?? "")) {
        cursor += 1;
      }
      if (REASON_PROPS.has(word) && source[cursor] === "=") {
        const value = readAttributeValue(source, cursor + 1);
        if (value != null) {
          const message = normalize(value);
          if (message.endsWith("。")) {
            found.push({
              file: relativeFile,
              line: lineOf(source, index),
              prop: word,
              message,
            });
          }
        }
      }
      index = end;
      continue;
    }

    index += 1;
  }

  return found;
}

function readAttributeValue(source: string, start: number): string | null {
  let index = start;
  while (index < source.length && /\s/.test(source[index] ?? "")) {
    index += 1;
  }
  const char = source[index];
  if (char === '"' || char === "'") {
    const end = skipString(source, index, char);
    return source.slice(index + 1, Math.max(index + 1, end - 1));
  }
  if (char === "{") {
    index += 1;
    while (index < source.length && /\s/.test(source[index] ?? "")) {
      index += 1;
    }
    const inner = source[index];
    if (inner === "`") {
      return readTemplate(source, index).text;
    }
    if (inner === '"' || inner === "'") {
      const end = skipString(source, index, inner);
      return source.slice(index + 1, Math.max(index + 1, end - 1));
    }
  }
  return null;
}

describe("無効理由の単一ソース性 (INV-004)", () => {
  it("走査対象の件数を下限で固定する（0 件なら無条件に緑にしない）", () => {
    const files = featureFiles();
    expect(
      files.length,
      `Expected >= ${EXPECTED_MIN_FEATURE_FILES} features files to be scanned, found ${files.length}`,
    ).toBeGreaterThanOrEqual(EXPECTED_MIN_FEATURE_FILES);
  });

  it("走査器は理由文の直書きを拾い、そうでない文は拾わない", () => {
    // 走査器そのものの正の対照。実ツリーから違反が消えても、この検査が
    // 通らなければ走査が空振りしていると分かる。
    const fixture = `
      function Blocker() {
        return <Notice message="この操作はまだできません。" />;
      }
      function Label() {
        return <Notice message="説明ラベル" />;
      }
      const assignment = "message=代入ではない。";
    `;
    const detected = detectReasons("fixture.tsx", fixture);
    expect(detected.map((reason) => reason.message)).toEqual([
      "この操作はまだできません。",
    ]);
  });

  it("features/ に core 以外で直書きされた無効理由が無い", () => {
    const allowed = new Set(
      OUTSTANDING_REASONS.map((entry) => normalize(entry.message)),
    );
    const detected = featureFiles().flatMap((file) =>
      detectReasons(file, readFileSync(path.join(PACKAGE_ROOT, file), "utf8")),
    );
    const unexpected = detected.filter(
      (reason) => !allowed.has(reason.message),
    );
    expect(
      unexpected.map(
        (reason) =>
          `${reason.file}:${reason.line} [${reason.prop}] ${reason.message}`,
      ),
    ).toEqual([]);
  });

  it("許容済みの無効理由は件数で固定する（allowlist を増やすと赤くなる）", () => {
    expect(OUTSTANDING_REASONS).toHaveLength(OUTSTANDING_REASON_COUNT);
    const messages = OUTSTANDING_REASONS.map((entry) =>
      normalize(entry.message),
    );
    expect(new Set(messages).size).toBe(messages.length);
  });
});

describe("無効理由文の文言規約 (INV-101)", () => {
  /**
   * 例外名・HTTP ステータスコード等の内部診断文が講師の目に触れないための形。
   * 3 桁の数字は HTTP ステータスを疑うが、件数 (`123件`) を弾かないよう
   * Flutter 版と同じく「数字 3 桁 + 空白」を診断文の合図にする。
   */
  const DIAGNOSTIC = /Exception|[Ee]rror|HTTP|[0-9]{3} /;

  function allRequirements(): ActionRequirement[] {
    return Object.values(ActionRequirements).map((value) =>
      typeof value === "function" ? value(1) : value,
    );
  }

  it("ActionRequirements の全メンバーを列挙できている", () => {
    const members = Object.keys(ActionRequirements);
    expect(members.length).toBeGreaterThan(0);
    expect(allRequirements()).toHaveLength(members.length);
  });

  it("理由 id は一意である", () => {
    const ids = allRequirements().map((requirement) => requirement.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("全理由文が「。」で終わり、例外名や HTTP ステータスコードを含まない", () => {
    for (const requirement of allRequirements()) {
      expect(requirement.id.length, "id が空").toBeGreaterThan(0);
      expect(
        requirement.message.length,
        `${requirement.id}: 文が空`,
      ).toBeGreaterThan(0);
      expect(
        requirement.message.endsWith("。"),
        `${requirement.id}: 1 文として閉じていない`,
      ).toBe(true);
      expect(
        requirement.message,
        `${requirement.id}: 診断文が混ざっている`,
      ).not.toMatch(DIAGNOSTIC);
    }
  });
});
