import { describe, expect, it } from "vitest";

import {
  MATERIAL_COVER_EPSILON,
  materialRowIsCovered,
  mergeMaterialRange,
  sameMaterialRanges,
} from "../src/renderer/core/material-read-ranges.js";

describe("mergeMaterialRange (INV-065, INV-066)", () => {
  it("INV-065: inserts into a gap without NaN corruption", () => {
    const merged = mergeMaterialRange(
      [
        [0, 0.1],
        [0.4, 0.5],
        [0.8, 0.9],
      ],
      0.2,
      0.3,
    );
    expect(merged).toEqual([
      [0, 0.1],
      [0.2, 0.3],
      [0.4, 0.5],
      [0.8, 0.9],
    ]);
    expect(merged.some((r) => Number.isNaN(r[0]) || Number.isNaN(r[1]))).toBe(
      false,
    );
  });

  it("converges when merging the same range twice", () => {
    const cases: [readonly [number, number][], number, number][] = [
      [[], 0, 1],
      [
        [
          [0, 0.1],
          [0.4, 0.5],
          [0.8, 0.9],
        ],
        0.2,
        0.3,
      ],
      [[[0.7969, 0.9573]], 0.0764, 0.0765],
    ];
    for (const [ranges, start, end] of cases) {
      const once = mergeMaterialRange(ranges, start, end);
      const twice = mergeMaterialRange(once, start, end);
      expect(sameMaterialRanges(once, twice)).toBe(true);
    }
  });

  it("INV-066: a row is covered only once both edges are reached", () => {
    expect(materialRowIsCovered(null)).toBe(false);
    expect(materialRowIsCovered([[0, 0.5]])).toBe(false);
    expect(materialRowIsCovered([[0.5, 1]])).toBe(false);
    expect(
      materialRowIsCovered([
        [0, 0.5],
        [0.5, 1],
      ]),
    ).toBe(false);
    expect(materialRowIsCovered([[0, 1]])).toBe(true);
  });

  it("rounding-sized gap still counts as touching", () => {
    const gap = 0.0005;
    expect(gap).toBeLessThan(MATERIAL_COVER_EPSILON);
    const merged = mergeMaterialRange([[0, 0.5]], 0.5 + gap, 1);
    expect(merged).toHaveLength(1);
    expect(materialRowIsCovered(merged)).toBe(true);
  });
});
