import type { JSX } from "react";

import {
  confidenceLevelLabel,
  confidenceLevelOf,
} from "../../core/confidence-level.js";

export interface ConfidenceBadgeProps {
  readonly label: string;
  readonly confidence: number;
  readonly testId: string;
}

export function ConfidenceBadge({
  label,
  confidence,
  testId,
}: ConfidenceBadgeProps): JSX.Element {
  const level = confidenceLevelOf(confidence);
  const percent = Math.round(confidence * 100);
  const levelLabel = confidenceLevelLabel(level);
  const showWarning = level === "low";

  return (
    <div
      data-testid={testId}
      className="flex items-center gap-xs text-sm"
      aria-label={`${label} ${percent}% ${levelLabel}`}
    >
      <span>
        {label}: {percent}% ({levelLabel})
      </span>
      {showWarning ? (
        <span
          className="text-attention"
          aria-hidden
          data-testid={`${testId}-icon`}
        >
          ⚠
        </span>
      ) : null}
    </div>
  );
}
