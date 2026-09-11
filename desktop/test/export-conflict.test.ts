import { describe, expect, it } from "vitest";

import {
  ExportConflictError,
  exportConflictFromResponse,
} from "../src/renderer/core/export-conflict.js";

/**
 * INV-205: a 409 must keep the sidecar's own refusal code and the question ids
 * it names, so callers tell the reviewer which remedy applies instead of
 * guessing (Issue #150).
 */
describe("exportConflictFromResponse", () => {
  it("keeps the refusal code and question ids from a 409 body", () => {
    const error = exportConflictFromResponse(409, {
      detail: {
        code: "no_room_for_score",
        message: "one or more questions have no area to write the score in",
        question_ids: ["q-3", "q-4"],
      },
    });

    expect(error).toBeInstanceOf(ExportConflictError);
    expect(error?.conflictCode).toBe("no_room_for_score");
    expect(error?.conflictQuestionIds).toEqual(["q-3", "q-4"]);
  });

  it("ignores a response that is not a conflict", () => {
    expect(exportConflictFromResponse(200, {})).toBeNull();
    expect(
      exportConflictFromResponse(401, { detail: "unauthorized" }),
    ).toBeNull();
  });

  it("keeps null/empty rather than inventing a code from a malformed 409", () => {
    const error = exportConflictFromResponse(409, { detail: "plain text" });

    expect(error?.conflictCode).toBeNull();
    expect(error?.conflictQuestionIds).toEqual([]);
  });
});
