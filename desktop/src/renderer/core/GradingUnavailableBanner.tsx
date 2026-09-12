import type { JSX, ReactNode } from "react";

import type { components } from "../api/generated/schema.js";
import { MaterialSymbolIcon } from "./MaterialSymbolIcon.js";

export type GradingAvailability =
  components["schemas"]["GradingAvailabilityResponse"];

/**
 * 「この端末では AI 採点が使えない」を全画面の上に出しっぱなしにする帯
 * (INV-168, Issue #272).
 *
 * It is shown **only** when the sidecar has answered and the answer is
 * `available: false`. While `availability` is `null` (never asked, or the
 * request did not come back) and when `available` is `true`, it renders its
 * child unchanged. Turning "no answer" into "this machine cannot grade" is the
 * mistake this control exists to prevent: one failed request would otherwise
 * become a configuration accusation.
 */
export function GradingUnavailableBanner({
  availability,
  children,
}: {
  readonly availability: GradingAvailability | null;
  readonly children?: ReactNode;
}): JSX.Element {
  if (availability === null || availability.available) {
    return <>{children}</>;
  }
  return (
    <div className="flex min-h-screen flex-col">
      <div
        data-testid="grading-unavailable-banner"
        role="status"
        className="flex items-start gap-sm bg-surface-container-highest p-lg"
      >
        <MaterialSymbolIcon
          name="warning_amber"
          label="警告"
          className="shrink-0 text-attention"
        />
        <div className="min-w-0 flex-1">
          <p
            data-testid="grading-unavailable-headline"
            className="text-body-medium font-medium text-on-surface"
          >
            AI採点は使えません（この端末に設定がありません）
          </p>
          <p className="mt-xs text-body-small text-on-surface-variant">
            答案取込・添削レビュー・PDF出力はこのまま使えます。取り込んだ答案の設問は採点されず「失敗」になります。
          </p>
          {availability.reason != null && availability.reason.length > 0 ? (
            <p
              data-testid="grading-unavailable-reason"
              className="mt-xs break-words text-body-small text-on-surface-variant"
            >
              {availability.reason}
            </p>
          ) : null}
        </div>
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
