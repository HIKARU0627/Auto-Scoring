/**
 * Export refusal handling (Issue #23 / #150 / INV-182..184).
 *
 * Conflict codes come from the sidecar — never guessed on the client.
 */

export const CONFLICT_UNCONFIRMED_QUESTIONS = "unconfirmed_questions";
export const CONFLICT_NO_ROOM_FOR_SCORE = "no_room_for_score";

export class ExportConflictError extends Error {
  constructor(
    message: string,
    readonly conflictCode: string | null,
    readonly conflictQuestionIds: readonly string[],
  ) {
    super(message);
    this.name = "ExportConflictError";
  }
}

export class ExportDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExportDataError";
  }
}

function detailRecord(detail: unknown): Record<string, unknown> | null {
  if (typeof detail !== "object" || detail === null) {
    return null;
  }
  return detail as Record<string, unknown>;
}

export function detailMessage(data: unknown): string | null {
  if (typeof data !== "object" || data === null) {
    return null;
  }
  const record = data as Record<string, unknown>;
  const detail = record["detail"];
  if (typeof detail === "string") {
    return detail;
  }
  const nested = detailRecord(detail);
  if (nested !== null && typeof nested["message"] === "string") {
    return nested["message"];
  }
  if (typeof record["message"] === "string") {
    return record["message"];
  }
  return null;
}

export function detailCode(data: unknown): string | null {
  if (typeof data !== "object" || data === null) {
    return null;
  }
  const record = data as Record<string, unknown>;
  const detail = detailRecord(record["detail"]);
  if (detail === null) {
    return null;
  }
  const code = detail["code"];
  return typeof code === "string" ? code : null;
}

export function detailQuestionIds(data: unknown): string[] {
  if (typeof data !== "object" || data === null) {
    return [];
  }
  const record = data as Record<string, unknown>;
  const detail = detailRecord(record["detail"]);
  if (detail === null) {
    return [];
  }
  const ids = detail["question_ids"];
  if (!Array.isArray(ids)) {
    return [];
  }
  return ids.filter((id): id is string => typeof id === "string");
}

export function exportConflictFromResponse(
  status: number,
  body: unknown,
): ExportConflictError | null {
  if (status !== 409) {
    return null;
  }
  const message = detailMessage(body) ?? "sidecar reported a conflict";
  return new ExportConflictError(
    message,
    detailCode(body),
    detailQuestionIds(body),
  );
}

/** Refusal headline — only known codes get tailored text (INV-184). */
export function refusalHeadline(conflictCode: string | null): string {
  switch (conflictCode) {
    case CONFLICT_UNCONFIRMED_QUESTIONS:
      return "未確認の設問があるため出力できません:";
    case CONFLICT_NO_ROOM_FOR_SCORE:
      return "点数を書き込める場所が無い設問があるため出力できません:";
    default:
      return "出力できません:";
  }
}

/**
 * What the reviewer should do next — differs per refusal kind (INV-183).
 * Unknown codes fall back to the sidecar's own message (INV-184).
 */
export function refusalDetail(
  conflictCode: string | null,
  sidecarMessage: string,
): string | null {
  switch (conflictCode) {
    case CONFLICT_UNCONFIRMED_QUESTIONS:
      return "上記の設問を確定させると出力できます。";
    case CONFLICT_NO_ROOM_FOR_SCORE:
      return "ページに点数を書き込める余白がありません。確定操作では解消しません。";
    default:
      return sidecarMessage;
  }
}

/** Bulk-export refusal line — aligned with single-export wording. */
export function bulkExportRefusalReason(
  refusalCode: string | null | undefined,
  questionIds: readonly string[],
): string {
  switch (refusalCode) {
    case CONFLICT_UNCONFIRMED_QUESTIONS:
      return `未確認の設問が${questionIds.length}問あります`;
    case CONFLICT_NO_ROOM_FOR_SCORE:
      return "点数を書き込める場所がありません (確定操作では解消しません)";
    default:
      return "サイドカーが出力を断りました";
  }
}
