import type { components } from "../api/generated/schema.js";

export type MaterialRole = components["schemas"]["MaterialRole"];

export function materialRoleLabel(role: MaterialRole): string {
  switch (role) {
    case "student_answer":
      return "生徒答案";
    case "grading_criteria":
      return "採点基準";
    case "annotation_resource":
      return "添削資料";
    case "annotation_sample":
      return "添削サンプル";
    case "reference":
      return "参考資料";
    case "ignore":
      return "取り込まない";
    default:
      return role;
  }
}
