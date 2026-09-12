import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import * as path from "node:path";

/**
 * `docs/frontend-invariants.md` §19「移行後に追加された不変条件」の行と集計を突き合わせる
 * (Issue #405)。
 *
 * §16〜§18 の 185 件は `frontend-invariants-tally.test.ts` が守っている。§19 はその
 * 集計に混ぜない別枠で、移行後に `desktop/` へ入った PR が固定した不変条件を積む。
 * ここでは §19.1 の行を唯一の真実とし、
 *
 * - 行 → §19.2 の区分別件数・合計（行だけ／集計だけを変えても赤くなる）
 * - 各行の ID が既存の `INV-\d+` を拾う正規表現に一致しないこと
 * - 各行が指すテストファイルと test 名が実在すること（テストの無い主張を防ぐ）
 *
 * を検査する。
 */

const REPO_ROOT = path.resolve(import.meta.dirname, "../..");
const DOC_PATH = path.join(REPO_ROOT, "docs/frontend-invariants.md");
const DOC_LABEL = "docs/frontend-invariants.md";
const ID_PATTERN = /^INV-E\d{3}$/;
/** 既存の棚卸し・照合表が使う番号体系。§19 の ID はこれに一致してはならない。 */
const LEGACY_ID_PATTERN = /^INV-\d/;

interface Section19Row {
  readonly id: string;
  readonly category: string;
  readonly invariant: string;
  readonly file: string;
  readonly testName: string;
  readonly origin: string;
}

function readDoc(): readonly string[] {
  let raw: string;
  try {
    raw = readFileSync(DOC_PATH, "utf8");
  } catch (error) {
    throw new Error(
      `${DOC_LABEL} を読めませんでした (${String(error)})。` +
        `パスはこのテストからの相対で固定している。ファイルを移動・改名したなら DOC_PATH を直すこと。`,
    );
  }
  return raw.split("\n");
}

function isTableRow(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.startsWith("|") && trimmed.endsWith("|");
}

function isSeparatorRow(line: string): boolean {
  return /^\|[\s:|-]+\|$/.test(line.trim()) && line.includes("-");
}

function cleanCell(cell: string): string {
  return cell.trim().replace(/\*\*/g, "").replace(/`/g, "").trim();
}

function cellAt(cells: readonly string[], index: number): string {
  return cells[index] ?? "";
}

function sectionLines(
  doc: readonly string[],
  heading: string,
): readonly string[] {
  const start = doc.findIndex((line) => line.startsWith(heading));
  if (start < 0) {
    throw new Error(
      `${DOC_LABEL} に「${heading}」で始まる見出しがありません。見出しを改名・削除したなら、このテストのセクション指定も更新すること。`,
    );
  }
  const level = (heading.match(/^#+/)?.[0] ?? "#").length;
  const out: string[] = [];
  for (let i = start + 1; i < doc.length; i += 1) {
    const match = /^(#+)\s/.exec(doc[i] ?? "");
    if (match && (match[1]?.length ?? 0) <= level) break;
    out.push(doc[i] ?? "");
  }
  return out;
}

interface MarkdownTable {
  readonly headers: readonly string[];
  readonly rows: readonly (readonly string[])[];
}

function parseTables(lines: readonly string[]): readonly MarkdownTable[] {
  const tables: MarkdownTable[] = [];
  let index = 0;
  while (index < lines.length) {
    if (!isTableRow(lines[index] ?? "")) {
      index += 1;
      continue;
    }
    const block: string[] = [];
    while (index < lines.length && isTableRow(lines[index] ?? "")) {
      block.push(lines[index] ?? "");
      index += 1;
    }
    const headers = (block[0] ?? "").split("|").slice(1, -1).map(cleanCell);
    const rows = block
      .slice(1)
      .filter((line) => !isSeparatorRow(line))
      .map((line) => line.split("|").slice(1, -1).map(cleanCell));
    tables.push({ headers, rows });
  }
  return tables;
}

function requireTable(
  tables: readonly MarkdownTable[],
  where: string,
  match: (table: MarkdownTable) => boolean,
): MarkdownTable {
  const table = tables.find(match);
  if (!table) {
    throw new Error(
      `${where} の表が見つかりません。表の見出しを変えたなら、このテストの探索条件も更新すること。`,
    );
  }
  return table;
}

function deriveRows(doc: readonly string[]): readonly Section19Row[] {
  const table = requireTable(
    parseTables(sectionLines(doc, "### 19.1")),
    "§19.1",
    (candidate) =>
      candidate.headers[0] === "ID" && candidate.headers.includes("test 名"),
  );
  const rows: Section19Row[] = [];
  for (const cells of table.rows) {
    rows.push({
      id: cellAt(cells, 0),
      category: cellAt(cells, 1),
      invariant: cellAt(cells, 2),
      file: cellAt(cells, 3),
      testName: cellAt(cells, 4),
      origin: cellAt(cells, 5),
    });
  }
  return rows;
}

function summaryCounts(doc: readonly string[]): ReadonlyMap<string, number> {
  const table = requireTable(
    parseTables(sectionLines(doc, "### 19.2")),
    "§19.2",
    (candidate) => candidate.headers[0] === "区分",
  );
  const counts = new Map<string, number>();
  for (const cells of table.rows) {
    const label = cellAt(cells, 0);
    const value = Number(cellAt(cells, 1).replace(/[,\s]/g, ""));
    if (!Number.isFinite(value)) {
      throw new Error(
        `§19.2 の「${label}」を数値として読めませんでした: 「${cellAt(cells, 1)}」`,
      );
    }
    counts.set(label, value);
  }
  return counts;
}

function countBy(values: readonly string[]): ReadonlyMap<string, number> {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return counts;
}

const doc = readDoc();
const rows = deriveRows(doc);
const summary = summaryCounts(doc);
const categoryCounts = countBy(rows.map((row) => row.category));

describe(`${DOC_LABEL} §19 の行と集計`, () => {
  it("ID は INV-E<3桁> で、既存の INV-\\d+ を拾う正規表現に一致しない", () => {
    const offending = rows
      .map((row) => row.id)
      .filter((id) => LEGACY_ID_PATTERN.test(id));
    expect(
      offending,
      `§19 の ID が既存の INV-\\d+ 体系と衝突しています: ${offending.join(", ")}。` +
        `§16〜§18 の走査に拾われるため、INV-E<3桁> の形にしてください。`,
    ).toEqual([]);
    for (const row of rows) {
      expect(
        ID_PATTERN.test(row.id),
        `§19.1 の ID「${row.id}」が INV-E<3桁> の形ではありません。`,
      ).toBe(true);
    }
  });

  it("ID は重複しない", () => {
    const ids = rows.map((row) => row.id);
    const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
    expect(
      duplicates,
      `§19.1 に同じ ID が複数回出ています: ${duplicates.join(", ")}。1 つの不変条件は 1 行にしてください。`,
    ).toEqual([]);
  });

  it("§19.1 の行と §19.2 の区分別件数が一致する", () => {
    for (const [category, declared] of summary) {
      if (category === "合計") continue;
      const derived = categoryCounts.get(category) ?? 0;
      expect(
        declared,
        `§19.2 の「${category}」が ${declared} 件ですが、§19.1 の行を数えると ${derived} 件です。` +
          `行の区分か §19.2 の件数を合わせてください。`,
      ).toBe(derived);
    }
    const unknown = [...categoryCounts.keys()].filter(
      (category) => !summary.has(category),
    );
    expect(
      unknown,
      `§19.1 に §19.2 の区分へ載っていない区分があります: ${unknown.join(", ")}。` +
        `行を足したなら §19.2 にも区分を足してください。`,
    ).toEqual([]);
  });

  it("§19.2 の合計は §19.1 の行数と一致する", () => {
    expect(
      summary.get("合計"),
      `§19.2 の合計が §19.1 の行数 ${rows.length} 件と一致しません。` +
        `行を足す／削ったのが意図どおりなら §19.2 の区分別件数と合計も更新してください。`,
    ).toBe(rows.length);
  });

  it("各行が指すテストファイルが実在する", () => {
    for (const row of rows) {
      const full = path.join(REPO_ROOT, row.file);
      expect(
        existsSync(full),
        `${row.id} が指すテストファイル「${row.file}」が存在しません。パスを直すか、テストが無いなら行を削ってください。`,
      ).toBe(true);
      expect(
        row.file.startsWith("desktop/"),
        `${row.id} のテストファイルはリポジトリルート相対で desktop/ から書いてください: 「${row.file}」`,
      ).toBe(true);
    }
  });

  it("各行が指す test 名がテストファイルに実在する", () => {
    for (const row of rows) {
      const full = path.join(REPO_ROOT, row.file);
      if (!existsSync(full)) continue;
      const source = readFileSync(full, "utf8");
      expect(
        source.includes(row.testName),
        `${row.id} が指す test 名「${row.testName}」が ${row.file} に見つかりません。` +
          `test 名を改名・削除したなら §19.1 を直し、テストが無いなら行を削ってください。`,
      ).toBe(true);
    }
  });
});
