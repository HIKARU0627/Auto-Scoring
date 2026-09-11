import { describe, expect, it } from "vitest";

import {
  materialRoleWireValue,
  PDF_CONTENT_TYPE,
} from "../src/renderer/core/intake-data.js";

describe("intake upload helpers (INV-134 / INV-135)", () => {
  it("INV-134: material roles use wire names", () => {
    expect(materialRoleWireValue("annotation_resource")).toBe(
      "annotation_resource",
    );
    expect(materialRoleWireValue("student_answer")).toBe("student_answer");
    expect(materialRoleWireValue("grading_criteria")).toBe("grading_criteria");
  });

  it("INV-135: PDF uploads declare application/pdf", () => {
    expect(PDF_CONTENT_TYPE).toBe("application/pdf");
  });
});
