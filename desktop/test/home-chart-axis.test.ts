import { describe, expect, it } from "vitest";

import { homeBarAxis } from "../src/renderer/core/home-analytics.js";

/**
 * Issue #382: the home daily bar chart must not draw its tallest bar against
 * the top of the plot. The axis upper bound and the labeled ticks come from one
 * pure function so the labels and the bars cannot disagree.
 *
 * The issued spec asked for "85-90% of the plot". That band is impossible for
 * every count -- `max / upper` wants `upper / max` in [1.111, 1.176], and for
 * `max = 10` no integer upper bound lands in [11.111, 11.765], while the next
 * `{1,2,5} * 10^n` value above 10 is 20 (50%). The accepted invariants are the
 * ones asserted below: at most 90% (always at least 10% headroom) and at least
 * 70% once the counts are large enough for an integer bound to be close.
 */

/** True for `mantissa * 10^n` with a mantissa in `{1, 2, 5}`. */
function isNiceStep(value: number): boolean {
  if (!(value >= 1)) {
    return false;
  }
  let rest = value;
  while (rest > 1 && Number.isInteger(rest)) {
    if (rest % 5 === 0) {
      rest /= 5;
    } else if (rest % 2 === 0) {
      rest /= 2;
    } else {
      break;
    }
  }
  return rest === 1;
}

describe("homeBarAxis (Issue #382)", () => {
  it("rounds each boundary count up to a nice bound with headroom", () => {
    // The commander's table, pinned exactly. A change to the step choice, the
    // 0.9 target, or the ceiling shows up here.
    expect(homeBarAxis(0)).toEqual({ upper: 1, step: 1, ticks: [0, 1] });
    expect(homeBarAxis(1)).toEqual({ upper: 2, step: 1, ticks: [0, 1, 2] });
    expect(homeBarAxis(3)).toEqual({
      upper: 4,
      step: 1,
      ticks: [0, 1, 2, 3, 4],
    });
    expect(homeBarAxis(9)).toEqual({
      upper: 10,
      step: 2,
      ticks: [0, 2, 4, 6, 8, 10],
    });
    expect(homeBarAxis(10)).toEqual({
      upper: 12,
      step: 2,
      ticks: [0, 4, 8, 12],
    });
    expect(homeBarAxis(11)).toEqual({
      upper: 14,
      step: 2,
      ticks: [0, 4, 8, 12, 14],
    });
    expect(homeBarAxis(17)).toEqual({
      upper: 20,
      step: 2,
      ticks: [0, 4, 8, 12, 16, 20],
    });
    expect(homeBarAxis(56)).toEqual({
      upper: 70,
      step: 10,
      ticks: [0, 20, 40, 60, 70],
    });
    expect(homeBarAxis(99)).toEqual({
      upper: 120,
      step: 20,
      ticks: [0, 40, 80, 120],
    });
    expect(homeBarAxis(100)).toEqual({
      upper: 120,
      step: 20,
      ticks: [0, 40, 80, 120],
    });
    expect(homeBarAxis(1000)).toEqual({
      upper: 1200,
      step: 200,
      ticks: [0, 400, 800, 1200],
    });
  });

  it("never lets the tallest bar touch the ceiling", () => {
    for (let max = 0; max <= 2000; max += 1) {
      const axis = homeBarAxis(max);
      if (max === 0) {
        expect(axis.upper).toBeGreaterThanOrEqual(1);
      } else {
        expect(axis.upper, `max=${max}`).toBeGreaterThan(max);
      }
    }
  });

  it("always leaves at least 10% headroom, and at most 30% once max >= 10", () => {
    for (let max = 1; max <= 2000; max += 1) {
      const axis = homeBarAxis(max);
      const ratio = max / axis.upper;
      expect(ratio, `max=${max}`).toBeLessThanOrEqual(0.9);
      if (max >= 10) {
        // Below 10 the {1,2,5} bounds are too far apart for an integer upper
        // bound to stay close; the accepted spec does not promise it there.
        expect(ratio, `max=${max}`).toBeGreaterThanOrEqual(0.7);
      }
    }
  });

  it("builds the bound from a {1,2,5} * 10^n step", () => {
    for (let max = 0; max <= 2000; max += 1) {
      const axis = homeBarAxis(max);
      expect(isNiceStep(axis.step), `max=${max} step=${axis.step}`).toBe(true);
      expect(axis.upper % axis.step, `max=${max}`).toBe(0);
      expect(Number.isInteger(axis.upper), `max=${max}`).toBe(true);
    }
  });

  it("labels the upper bound with 3-6 ascending ticks that include it", () => {
    for (let max = 1; max <= 2000; max += 1) {
      const axis = homeBarAxis(max);
      const { ticks } = axis;
      expect(ticks.length, `max=${max}`).toBeGreaterThanOrEqual(3);
      expect(ticks.length, `max=${max}`).toBeLessThanOrEqual(6);
      expect(ticks[0], `max=${max}`).toBe(0);
      expect(ticks[ticks.length - 1], `max=${max}`).toBe(axis.upper);
      for (let index = 1; index < ticks.length; index += 1) {
        const current = ticks[index];
        const previous = ticks[index - 1];
        if (current === undefined || previous === undefined) {
          throw new Error(`max=${max} lost a tick`);
        }
        expect(current, `max=${max}`).toBeGreaterThan(previous);
      }
      for (const tick of ticks) {
        expect(tick % axis.step, `max=${max} tick=${tick}`).toBe(0);
      }
    }
  });

  it("does not divide by zero or produce NaN for all-zero data", () => {
    const axis = homeBarAxis(0);
    expect(Number.isFinite(axis.upper)).toBe(true);
    expect(axis.upper).toBeGreaterThan(0);
    for (const tick of axis.ticks) {
      expect(Number.isFinite(tick)).toBe(true);
      expect(tick).toBeGreaterThanOrEqual(0);
    }
    const ratio = 0 / axis.upper;
    expect(Number.isNaN(ratio)).toBe(false);
  });

  it("treats a non-finite count as the empty chart instead of returning NaN", () => {
    expect(homeBarAxis(Number.NaN)).toEqual({
      upper: 1,
      step: 1,
      ticks: [0, 1],
    });
    expect(homeBarAxis(-5)).toEqual({ upper: 1, step: 1, ticks: [0, 1] });
  });
});
