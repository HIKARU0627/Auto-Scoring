import type { MaterialSymbolName } from "./material-symbols.js";

/**
 * Visual presentation for a submission's state (`SubmissionResponse.state`).
 *
 * Keeps label, icon, and tone in one place so intake, review queue, and review
 * screens do not drift in terminology (Issue #84 / INV-097). The three travel
 * together: the icon is typed as {@link MaterialSymbolName} so a state cannot
 * name a glyph the SVG table does not draw (Issue #397).
 */

export type SubmissionStatusTone =
  "attention" | "neutral" | "danger" | "success";

export interface SubmissionStatusVisual {
  readonly label: string;
  readonly tone: SubmissionStatusTone;
  readonly icon: MaterialSymbolName;
}

/** Tailwind text colour for a tone, shared by the queue row and confirm chip. */
export function submissionStatusToneTextClass(
  tone: SubmissionStatusTone,
): string {
  switch (tone) {
    case "attention":
      return "text-attention";
    case "danger":
      return "text-error";
    case "success":
      return "text-success";
    default:
      return "text-on-surface-variant";
  }
}

export function submissionStatusVisualOf(
  state: string | null | undefined,
): SubmissionStatusVisual {
  switch (state) {
    case null:
    case undefined:
    case "unprocessed":
      return {
        label: "未処理",
        tone: "neutral",
        icon: "hourglass_empty",
      };
    case "ai_processing":
      return {
        label: "AI処理中",
        tone: "neutral",
        icon: "autorenew",
      };
    case "ai_processed":
      return {
        label: "AI処理済み",
        tone: "success",
        icon: "check_circle",
      };
    case "needs_review":
      return {
        label: "要確認",
        tone: "attention",
        icon: "warning_amber",
      };
    case "reviewed":
      return {
        label: "確認済み",
        tone: "success",
        icon: "verified",
      };
    case "exported":
      return {
        label: "出力済み",
        tone: "success",
        icon: "file_download_done",
      };
    case "error":
      return {
        label: "エラー",
        tone: "danger",
        icon: "error_outline",
      };
    default:
      return {
        label: state,
        tone: "neutral",
        icon: "help_outline",
      };
  }
}
