import type { JSX } from "react";

import { MaterialSymbolIcon } from "./MaterialSymbolIcon.js";
import {
  QuestionStatus,
  type QuestionStatusKey,
  type QuestionStatusTone,
} from "./question-status.js";

/**
 * Badge for a per-question status (INV-097, Issue #272).
 *
 * Colour only sharpens a distinction that must already survive without it, so
 * every state carries its own Japanese label and its own icon. The label and
 * icon come from `QuestionStatus`, the single source of truth; a state added
 * there without a distinct pair fails the presentation test of
 * `desktop/test/renderer/question-status-badge.test.tsx`.
 */

const TONE_CLASS: Record<QuestionStatusTone, string> = {
  neutral: "text-on-surface-variant",
  attention: "text-attention",
  danger: "text-error",
  success: "text-success",
};

export interface QuestionStatusBadgeProps {
  readonly status: QuestionStatusKey;
  readonly testId?: string;
}

export function QuestionStatusBadge({
  status,
  testId,
}: QuestionStatusBadgeProps): JSX.Element {
  const meta = QuestionStatus[status];
  return (
    <span
      data-testid={testId}
      data-status={status}
      className={`inline-flex items-center gap-xs text-ui-label ${TONE_CLASS[meta.tone]}`}
    >
      <MaterialSymbolIcon
        name={meta.icon}
        label={meta.label}
        testId={testId === undefined ? undefined : `${testId}-icon`}
      />
      <span
        aria-hidden
        data-testid={testId === undefined ? undefined : `${testId}-label`}
      >
        {meta.label}
      </span>
    </span>
  );
}
