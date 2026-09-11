import { act, renderHook } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it } from "vitest";

import {
  useMaterialReadTracking,
  type MaterialRowsInput,
} from "../../src/renderer/features/pdf-review/use-material-read-tracking.js";

describe("useMaterialReadTracking", () => {
  it("treats unknown material rows as not covered (fail-closed)", () => {
    const scrollContainerRef = createRef<HTMLElement | null>();
    const input: MaterialRowsInput = { status: "unknown" };
    const { result } = renderHook(() =>
      useMaterialReadTracking(input, scrollContainerRef),
    );
    expect(result.current.allRowsCovered).toBe(false);
  });

  it("revealRest shows snackbar when scroll container is null", () => {
    const scrollContainerRef = createRef<HTMLElement | null>();
    const input: MaterialRowsInput = {
      status: "known",
      rows: [{ id: "grade:test" }],
    };
    const { result } = renderHook(() =>
      useMaterialReadTracking(input, scrollContainerRef),
    );
    act(() => {
      result.current.revealRest();
    });
    expect(result.current.snackbarMessage).toContain(
      "判断材料が画面外に残っていました",
    );
  });
});
