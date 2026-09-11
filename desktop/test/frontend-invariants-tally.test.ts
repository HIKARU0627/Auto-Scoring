import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import * as path from "node:path";

/**
 * `docs/frontend-invariants.md` の引き取り集計が、個々の不変条件の行（§17.4 の
 * 「状態」列）から導出した数と一致することを固定する (Issue #290)。
 *
 * 背景: この文書の集計表は PR が 1 本入るたびに動く。§17.1 / §17.2 / §17.3 / §18 に
 * 同じ数が手書きで重複していたため、どの PR も同じ行で衝突し、さらに「集計だけ直して
 * 行を直し忘れる」事故を誰も検出できなかった。ここでは §17.4 の行を唯一の真実
 * (single source of truth) とし、すべての集計を数え直して突き合わせる。
 *
 * 集計値そのものは `EXPECTED` に集約して固定する。不変条件を引き取った PR は
 * §17.4 の該当行の「状態」を書き換えたうえで、テストが指し示す不一致を直せばよい。
 * 否定形が空振りしないよう、走査した行数も合わせて固定する。
 */

const DOC_PATH = path.resolve(
  import.meta.dirname,
  "../../docs/frontend-invariants.md",
);

const DOC_LABEL = "docs/frontend-invariants.md";

/**
 * 文書に固定する集計値（唯一の期待値）。
 *
 * 期待値をこの 1 箇所に集約し、文書中の集計はすべてここか §17.4 の行から導出した値と
 * 突き合わせる。ここが赤くなったときは、行を足す／削る変更か、状態の変更が意図どおりかを
 * 最初に確認する。
 */
const EXPECTED = {
  total: 185,
  inv: 170,
  ug: 15,
  claimed: 137,
  unclaimed: 48,
  prUnitClaimed: 130,
  issueNamedClaimed: 7,
  evidencePrRows: 14,
  unclaimedScreen: 21,
  unclaimedCommonInfra: 27,
  unmigratedScreens: 20,
  snapshotGap: 28,
  classificationTotal: 52,
  classificationA: 7,
  classificationB: 10,
  classificationC: 35,
} as const;

interface MarkdownTable {
  readonly headers: readonly string[];
  readonly rows: readonly (readonly string[])[];
}

interface InvariantRow {
  readonly id: string;
  readonly kind: "INV" | "UG";
  readonly area: string;
  readonly assignment: string;
  readonly claimed: boolean;
  readonly source: string;
}

interface Tally {
  readonly rows: readonly InvariantRow[];
  readonly inv: number;
  readonly ug: number;
  readonly total: number;
  readonly claimed: number;
  readonly unclaimed: number;
  readonly duplicateIds: readonly string[];
  readonly prGroups: ReadonlyMap<number, readonly string[]>;
  readonly issueGroups: ReadonlyMap<number, readonly string[]>;
  readonly unknownSources: readonly { id: string; source: string }[];
  readonly unclaimedByArea: ReadonlyMap<string, number>;
}

function readDoc(): readonly string[] {
  let raw: string;
  try {
    raw = readFileSync(DOC_PATH, "utf8");
  } catch (error) {
    throw new Error(
      `${DOC_LABEL} を読めませんでした (${String(error)})。` +
        `パスはテストからの相対で固定している。ファイルを移動・改名したならテストの DOC_PATH を直すこと。`,
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
      `${DOC_LABEL} に「${heading}」で始まる見出しがありません。` +
        `見出しを改名・削除したなら、このテストのセクション指定も更新すること。`,
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

function toCount(text: string, where: string): number {
  const normalized = text.replace(/[,\s]/g, "");
  const value = Number(normalized);
  if (!Number.isFinite(value)) {
    throw new Error(`${where} を数値として読めませんでした: 「${text}」`);
  }
  return value;
}

function numberNear(text: string, pattern: RegExp, where: string): number {
  const match = pattern.exec(text);
  const captured = match?.[1];
  if (captured === undefined) {
    throw new Error(
      `${where} の数値を読み取れませんでした。集計を書き換えた／文言を変えたなら、` +
        `テストの抽出条件も合わせること。`,
    );
  }
  return Number(captured);
}

function countBy(values: readonly string[]): ReadonlyMap<string, number> {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return counts;
}

function parseSource(
  source: string,
): { kind: "pr" | "issue"; number: number } | { kind: "unknown" } {
  const pr = /^PR #(\d+)/.exec(source);
  if (pr?.[1] !== undefined) return { kind: "pr", number: Number(pr[1]) };
  const issue = /^Issue #(\d+)/.exec(source);
  if (issue?.[1] !== undefined) {
    return { kind: "issue", number: Number(issue[1]) };
  }
  return { kind: "unknown" };
}

function deriveTally(doc: readonly string[]): Tally {
  const table = requireTable(
    parseTables(sectionLines(doc, "### 17.4")),
    "§17.4",
    (candidate) =>
      candidate.headers[0] === "ID" && candidate.headers.includes("状態"),
  );
  const rows: InvariantRow[] = [];
  for (const cells of table.rows) {
    const id = cellAt(cells, 0);
    if (!/^(INV|UG)-/.test(id)) continue;
    const state = cellAt(cells, 3);
    if (state !== "引き取り済み" && state !== "未引き取り") {
      throw new Error(
        `§17.4 の ${id} の「状態」が「引き取り済み」でも「未引き取り」でもありません: 「${state}」。` +
          `新しい状態を足したなら、このテストの数え方を更新すること。`,
      );
    }
    rows.push({
      id,
      kind: id.startsWith("INV-") ? "INV" : "UG",
      area: cellAt(cells, 1),
      assignment: cellAt(cells, 2),
      claimed: state === "引き取り済み",
      source: cellAt(cells, 4),
    });
  }

  const claimedRows = rows.filter((row) => row.claimed);
  const prGroups = new Map<number, string[]>();
  const issueGroups = new Map<number, string[]>();
  const unknownSources: { id: string; source: string }[] = [];
  for (const row of claimedRows) {
    const parsed = parseSource(row.source);
    if (parsed.kind === "unknown") {
      unknownSources.push({ id: row.id, source: row.source });
      continue;
    }
    const groups = parsed.kind === "pr" ? prGroups : issueGroups;
    const ids = groups.get(parsed.number);
    if (ids) ids.push(row.id);
    else groups.set(parsed.number, [row.id]);
  }

  const ids = rows.map((row) => row.id);
  const duplicateIds = ids.filter((id, i) => ids.indexOf(id) !== i);
  const unclaimedRows = rows.filter((row) => !row.claimed);

  return {
    rows,
    inv: rows.filter((row) => row.kind === "INV").length,
    ug: rows.filter((row) => row.kind === "UG").length,
    total: rows.length,
    claimed: claimedRows.length,
    unclaimed: unclaimedRows.length,
    duplicateIds,
    prGroups,
    issueGroups,
    unknownSources,
    unclaimedByArea: countBy(unclaimedRows.map((row) => row.area)),
  };
}

function sumGroups(groups: ReadonlyMap<number, readonly string[]>): number {
  let total = 0;
  for (const ids of groups.values()) total += ids.length;
  return total;
}

function findLine(lines: readonly string[], needle: string): string {
  const line = lines.find((candidate) => candidate.includes(needle));
  if (line === undefined) {
    throw new Error(
      `§17.3 / §18 に「${needle}」を含む行がありません。文言を変えたなら、このテストの抽出条件も更新すること。`,
    );
  }
  return line;
}

function section172Summary(
  doc: readonly string[],
): ReadonlyMap<string, number> {
  const table = requireTable(
    parseTables(sectionLines(doc, "### 17.2")),
    "§17.2",
    (candidate) => candidate.headers[0] === "状態区分",
  );
  const summary = new Map<string, number>();
  for (const cells of table.rows) {
    const label = cellAt(cells, 0);
    summary.set(label, toCount(cellAt(cells, 1), `§17.2 の「${label}」`));
  }
  return summary;
}

function section164Groups(
  doc: readonly string[],
): ReadonlyMap<string, { inv: number; ug: number; total: number }> {
  const table = requireTable(
    parseTables(sectionLines(doc, "### 16.4")),
    "§16.4",
    (candidate) => candidate.headers[0] === "大区分",
  );
  const groups = new Map<string, { inv: number; ug: number; total: number }>();
  for (const cells of table.rows) {
    const label = cellAt(cells, 0);
    groups.set(label, {
      inv: toCount(cellAt(cells, 1), `§16.4 の「${label}」INV 件数`),
      ug: toCount(cellAt(cells, 2), `§16.4 の「${label}」UG 件数`),
      total: toCount(cellAt(cells, 3), `§16.4 の「${label}」合計件数`),
    });
  }
  return groups;
}

function section165Groups(
  doc: readonly string[],
): ReadonlyMap<string, { inv: number; ug: number }> {
  const table = requireTable(
    parseTables(sectionLines(doc, "### 16.5")),
    "§16.5",
    (candidate) => candidate.headers[0] === "ID",
  );
  const groups = new Map<string, { inv: number; ug: number }>();
  for (const cells of table.rows) {
    const id = cellAt(cells, 0);
    if (!/^(INV|UG)-/.test(id)) continue;
    const area = cellAt(cells, 1);
    const group = groups.get(area) ?? { inv: 0, ug: 0 };
    if (id.startsWith("INV-")) group.inv += 1;
    else group.ug += 1;
    groups.set(area, group);
  }
  return groups;
}

function section181Counts(doc: readonly string[]): ReadonlyMap<string, number> {
  const table = requireTable(
    parseTables(sectionLines(doc, "### 18.1")),
    "§18.1",
    (candidate) =>
      candidate.headers[0] === "ID" && candidate.headers.includes("分類"),
  );
  const classes: string[] = [];
  for (const cells of table.rows) {
    const id = cellAt(cells, 0);
    if (/^(INV|UG)-/.test(id)) classes.push(cellAt(cells, 2));
  }
  return countBy(classes);
}

const doc = readDoc();
const tally = deriveTally(doc);

describe(`${DOC_LABEL} の引き取り集計`, () => {
  it("§17.4 の行は INV 170 + UG 15 = 185 件（行を足す／削ると赤くなる）", () => {
    expect(
      tally.inv,
      `不変条件 INV の行数が §17.4 で ${tally.inv} 件です。` +
        `EXPECTED.inv = ${EXPECTED.inv} と一致するよう、§17.4 の行を見直してください。`,
    ).toBe(EXPECTED.inv);
    expect(
      tally.ug,
      `UG の行数が §17.4 で ${tally.ug} 件です。` +
        `EXPECTED.ug = ${EXPECTED.ug} と一致するよう、§17.4 の行を見直してください。`,
    ).toBe(EXPECTED.ug);
    expect(
      tally.total,
      `§17.4 の行数が ${tally.total} 件です。不変条件の合計は INV ${EXPECTED.inv} + UG ${EXPECTED.ug} = ${EXPECTED.total} 件で固定しています。` +
        `行を足した／削ったのが意図どおりなら EXPECTED.total を更新し、§16.4・§17.2 の合計も同じ値にそろえてください。`,
    ).toBe(EXPECTED.total);
  });

  it("§17.4 の「状態」列は §17.2 の引き取り済み／未引き取りと一致する", () => {
    const summary = section172Summary(doc);
    const tableClaimed = summary.get("引き取り済み");
    const tableUnclaimed = summary.get("未引き取り");
    const tableTotal = summary.get("合計");

    expect(
      tally.claimed,
      `§17.4 の「状態」列を数えると引き取り済み ${tally.claimed} 件ですが、EXPECTED.claimed = ${EXPECTED.claimed} と違います。` +
        `行の状態を書き換えたのなら §17.2 の引き取り済みも更新してください。`,
    ).toBe(EXPECTED.claimed);
    expect(
      tally.unclaimed,
      `§17.4 の「状態」列を数えると未引き取り ${tally.unclaimed} 件ですが、EXPECTED.unclaimed = ${EXPECTED.unclaimed} と違います。`,
    ).toBe(EXPECTED.unclaimed);

    expect(
      tableClaimed,
      `§17.2 の引き取り済みが ${String(tableClaimed)} 件ですが、§17.4 の行から数えると ${tally.claimed} 件です。` +
        `数字を合わせるために行を書き換えず、§17.4 の「状態」列を正として §17.2 を ${tally.claimed} に直してください。`,
    ).toBe(tally.claimed);
    expect(
      tableUnclaimed,
      `§17.2 の未引き取りが ${String(tableUnclaimed)} 件ですが、§17.4 の行から数えると ${tally.unclaimed} 件です。` +
        `§17.2 を ${tally.unclaimed} に直すか、§17.4 の状態列を見直してください。`,
    ).toBe(tally.unclaimed);
    expect(
      tableTotal,
      `§17.2 の合計が ${String(tableTotal)} 件ですが、§17.4 の行から数えると ${tally.total} 件です。`,
    ).toBe(tally.total);
  });

  it("§17.4 の ID は重複しない（§17.2 の二重計上 0 件）", () => {
    const summary = section172Summary(doc);
    expect(
      tally.duplicateIds,
      `§17.4 に同じ ID が複数回出ています: ${tally.duplicateIds.join(", ")}。` +
        `1 つの不変条件は 1 行にしてください（二重計上は 0 件が前提）。`,
    ).toEqual([]);
    expect(
      summary.get("二重計上"),
      `§17.2 の二重計上が ${String(summary.get("二重計上"))} 件ですが、§17.4 に重複 ID はありません。`,
    ).toBe(tally.duplicateIds.length);
  });

  it("§17.1 の PR 別証跡は §17.4 の PR 引き取り行と一致し、非 PR 分は含めない", () => {
    expect(
      tally.unknownSources,
      `§17.4 の引き取り元が「PR #<番号>」でも「Issue #<番号>」でもない行があります: ` +
        `${tally.unknownSources.map((entry) => `${entry.id}=${entry.source}`).join(", ")}。` +
        `PR 単位の引き取りは「PR #<番号>」、Issue 名義は「Issue #<番号>」と書いてください（§17.1 と §17.2 の差の根拠になります）。`,
    ).toEqual([]);

    const table = requireTable(
      parseTables(sectionLines(doc, "### 17.1")),
      "§17.1",
      (candidate) => candidate.headers[0] === "PR",
    );
    const evidenceRows = table.rows.filter(
      (cells) => cellAt(cells, 0) !== "合計",
    );
    let declaredSum = 0;
    for (const cells of evidenceRows) {
      const label = cellAt(cells, 0);
      const numberMatch = /#(\d+)/.exec(label);
      if (!numberMatch?.[1]) {
        throw new Error(
          `§17.1 の PR 列「${label}」から PR 番号を読めません。` +
            `「#<番号>」の形に統一してください（§17.4 の引き取り元と突き合わせます）。`,
        );
      }
      const pr = Number(numberMatch[1]);
      const declared = toCount(cellAt(cells, 2), `§17.1 の ${label} 宣言件数`);
      declaredSum += declared;
      const derived = tally.prGroups.get(pr)?.length ?? 0;
      expect(
        declared,
        `§17.1 の ${label} は ${declared} 件と宣言していますが、§17.4 で PR #${pr} が引き取った行は ${derived} 件です。` +
          `§17.1 の宣言件数と §17.4 の「引き取り元」を一致させてください。`,
      ).toBe(derived);
    }

    expect(
      evidenceRows.length,
      `§17.1 の PR 行が ${evidenceRows.length} 行です。EXPECTED.evidencePrRows = ${EXPECTED.evidencePrRows} を超えて増減したなら、` +
        `§17.4 の引き取り元と §17.2 の引き取り済みを同時に見直してください。`,
    ).toBe(EXPECTED.evidencePrRows);
    expect(
      declaredSum,
      `§17.1 の宣言件数の合計が ${declaredSum} 件ですが、EXPECTED.prUnitClaimed = ${EXPECTED.prUnitClaimed} と違います。` +
        `§17.4 の PR 引き取り行（Issue 名義を除く）の合計が ${sumGroups(tally.prGroups)} 件であることを確認してください。`,
    ).toBe(EXPECTED.prUnitClaimed);
  });

  it("§17.1 と §17.2 の差は「PR 単位でない引き取り」で説明できる", () => {
    const summary = section172Summary(doc);
    const prUnit = sumGroups(tally.prGroups);
    const issueNamed = sumGroups(tally.issueGroups);
    const claimed = summary.get("引き取り済み");

    expect(
      prUnit,
      `§17.4 の PR 単位の引き取りが ${prUnit} 件で、EXPECTED.prUnitClaimed = ${EXPECTED.prUnitClaimed} と違います。`,
    ).toBe(EXPECTED.prUnitClaimed);
    expect(
      issueNamed,
      `§17.4 の Issue 名義の引き取りが ${issueNamed} 件で、EXPECTED.issueNamedClaimed = ${EXPECTED.issueNamedClaimed} と違います。`,
    ).toBe(EXPECTED.issueNamedClaimed);
    expect(
      claimed,
      `§17.2 の引き取り済み ${String(claimed)} 件は、§17.1 の PR 単位 ${prUnit} 件 + Issue 名義 ${issueNamed} 件 = ${prUnit + issueNamed} 件と一致しません。` +
        `PR 単位でない引き取りは §17.1 には載せず §17.2 に含める、という規則です（§17.0）。`,
    ).toBe(prUnit + issueNamed);
  });

  it("§17.3 の未引き取り内訳は §17.4 の区分から導出できる", () => {
    const lines = sectionLines(doc, "### 17.3");
    const text = lines.join("\n");

    const screen = tally.unclaimedByArea.get("画面") ?? 0;
    const commonInfra = tally.unclaimedByArea.get("共通基盤") ?? 0;
    expect(
      screen,
      `§17.4 の未引き取りで区分「画面」は ${screen} 件です。EXPECTED.unclaimedScreen = ${EXPECTED.unclaimedScreen} と一致するよう区分を見直してください。`,
    ).toBe(EXPECTED.unclaimedScreen);
    expect(
      commonInfra,
      `§17.4 の未引き取りで区分「共通基盤」は ${commonInfra} 件です。EXPECTED.unclaimedCommonInfra = ${EXPECTED.unclaimedCommonInfra} と一致するよう区分を見直してください。`,
    ).toBe(EXPECTED.unclaimedCommonInfra);
    expect(
      screen + commonInfra,
      `§17.4 の未引き取りは 画面 ${screen} + 共通基盤 ${commonInfra} = ${screen + commonInfra} 件で、§17.2 の未引き取り ${tally.unclaimed} 件と一致しません。`,
    ).toBe(tally.unclaimed);

    expect(
      numberNear(
        text,
        /未引き取り全\s*(\d+)\s*件/,
        "§17.3 の「未引き取り全 N 件」",
      ),
      `§17.3 の「未引き取り全 N 件」が §17.4 の未引き取り ${tally.unclaimed} 件と一致しません。`,
    ).toBe(tally.unclaimed);
    expect(
      numberNear(
        text,
        /画面側の残余:\s*(\d+)\s*件/,
        "§17.3 の「画面側の残余」",
      ),
      `§17.3 の「画面側の残余」が §17.4 の区分「画面」の未引き取り ${screen} 件と一致しません。`,
    ).toBe(screen);
    expect(
      numberNear(
        text,
        /共通基盤側の残余:\s*(\d+)\s*件/,
        "§17.3 の「共通基盤側の残余」",
      ),
      `§17.3 の「共通基盤側の残余」が §17.4 の区分「共通基盤」の未引き取り ${commonInfra} 件と一致しません。`,
    ).toBe(commonInfra);

    const unmigrated = tally.rows.filter(
      (row) =>
        !row.claimed &&
        (row.assignment === "答案確定" ||
          row.assignment === "設定" ||
          row.assignment === "出力"),
    ).length;
    expect(
      unmigrated,
      `§17.4 の未移植 3 画面（答案確定・設定・出力）は ${unmigrated} 件です。EXPECTED.unmigratedScreens = ${EXPECTED.unmigratedScreens} と違います。`,
    ).toBe(EXPECTED.unmigratedScreens);
    const gap = numberNear(text, /(\d+)\s*件の差/, "§17.3 の「N 件の差」");
    expect(
      gap,
      `§17.3 の「N 件の差」は未引き取り ${tally.unclaimed} 件 - 未移植 3 画面 ${unmigrated} 件 = ${tally.unclaimed - unmigrated} 件のはずです。`,
    ).toBe(tally.unclaimed - unmigrated);
  });

  it("§16.4 の割当内訳は §16.5 の行から導出できる", () => {
    const assigned = section165Groups(doc);
    const totals = section164Groups(doc);

    const screen = totals.get("画面（Phase 3 および Phase 2-4 ホーム）");
    const commonInfra = totals.get("共通基盤");
    const preTaken = totals.get("引き取り済み（Phase 2-2 / PR #225）");
    const grand = totals.get("合計");

    expect(
      assigned.get("画面"),
      `§16.5 の区分「画面」は §16.4 の大区分別の「画面」と一致しません。`,
    ).toEqual({ inv: screen?.inv, ug: screen?.ug });
    expect(
      assigned.get("共通基盤"),
      `§16.5 の区分「共通基盤」は §16.4 の大区分別の「共通基盤」と一致しません。`,
    ).toEqual({ inv: commonInfra?.inv, ug: commonInfra?.ug });
    expect(
      assigned.get("引き取り済み"),
      `§16.5 の区分「引き取り済み」は §16.4 の大区分別の「引き取り済み」と一致しません。`,
    ).toEqual({ inv: preTaken?.inv, ug: preTaken?.ug });

    const assignedInv = [...assigned.values()].reduce(
      (sum, g) => sum + g.inv,
      0,
    );
    const assignedUg = [...assigned.values()].reduce((sum, g) => sum + g.ug, 0);
    expect(
      grand,
      `§16.4 の合計が INV ${String(grand?.inv)} + UG ${String(grand?.ug)} = ${String(grand?.total)} ですが、` +
        `§16.5 の行は INV ${assignedInv} + UG ${assignedUg} = ${assignedInv + assignedUg} 件です。`,
    ).toEqual({
      inv: assignedInv,
      ug: assignedUg,
      total: assignedInv + assignedUg,
    });
    expect(
      grand?.total,
      `§16.4 の合計 ${String(grand?.total)} 件が §17.4 の行数 ${tally.total} 件と一致しません。`,
    ).toBe(tally.total);
  });

  it("§18 の分類件数（A / B / C）は §18.1 の分類列から導出できる", () => {
    const counts = section181Counts(doc);
    const a = counts.get("A") ?? -1;
    const b = counts.get("B") ?? -1;
    const c = counts.get("C") ?? -1;
    const total = a + b + c;

    expect(
      [a, b, c, total],
      `§18.1 の分類列を数えると A ${a} / B ${b} / C ${c} = ${total} 件です。` +
        `EXPECTED は A ${EXPECTED.classificationA} / B ${EXPECTED.classificationB} / C ${EXPECTED.classificationC} = ${EXPECTED.classificationTotal} 件です。`,
    ).toEqual([
      EXPECTED.classificationA,
      EXPECTED.classificationB,
      EXPECTED.classificationC,
      EXPECTED.classificationTotal,
    ]);

    const summary = requireTable(
      parseTables(sectionLines(doc, "## 18.")),
      "§18 の分類サマリ",
      (candidate) => candidate.headers[0] === "分類",
    );
    for (const cells of summary.rows) {
      const label = cellAt(cells, 0);
      const value = toCount(cellAt(cells, 2), `§18 の「${label}」件数`);
      const expected = label.startsWith("A")
        ? a
        : label.startsWith("B")
          ? b
          : label.startsWith("C")
            ? c
            : total;
      expect(
        value,
        `§18 の分類サマリ「${label}」が ${value} 件ですが、§18.1 の分類列から数えると ${expected} 件です。`,
      ).toBe(expected);
    }

    const preamble = findLine(
      sectionLines(doc, "## 18."),
      "共通基盤の未引き取り",
    );
    expect(
      numberNear(
        preamble,
        /未引き取り\s*\*{0,2}(\d+)\*{0,2}\s*件/,
        "§18 の未引き取り件数",
      ),
      `§18 の「共通基盤の未引き取り N 件」が §18.1 の合計 ${total} 件と一致しません。`,
    ).toBe(total);

    const codeBlock = sectionLines(doc, "### 18.5").join("\n");
    expect(
      numberNear(codeBlock, /分類\s*A.*?(\d+)\s*件/, "§18.5 の分類 A"),
      `§18.5 の分類 A の件数が §18.1 から数えた ${a} 件と一致しません。`,
    ).toBe(a);
    expect(
      numberNear(codeBlock, /分類\s*B.*?(\d+)\s*件/, "§18.5 の分類 B"),
      `§18.5 の分類 B の件数が §18.1 から数えた ${b} 件と一致しません。`,
    ).toBe(b);
    expect(
      numberNear(codeBlock, /分類\s*C.*?(\d+)\s*件/, "§18.5 の分類 C"),
      `§18.5 の分類 C の件数が §18.1 から数えた ${c} 件と一致しません。`,
    ).toBe(c);
  });
});
