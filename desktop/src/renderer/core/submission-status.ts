/**
 * Visual presentation for a submission's state (`SubmissionResponse.state`).
 *
 * Keeps label, icon, and tone in one place so intake, review queue, and review
 * screens do not drift in terminology (Issue #84 / INV-097).
 */

export interface SubmissionStatusVisual {
  readonly label: string;
  readonly tone: "attention" | "neutral" | "danger" | "success";
  readonly icon: string;
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
        icon: "check_circle_outline",
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
        icon: "verified_outlined",
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
