import type { JSX } from "react";
import { ArrowRight, FileText } from "lucide-react";

import type { HomeNextAction } from "../../core/home-dashboard.js";

/**
 * 「次の一手」hero card (Issue #336, parent #333 §5). The one thing to press
 * now: a purple icon tile, the headline and reason, and the primary action on
 * the right (it moves under the text on narrow windows).
 *
 * The tile stays the primary purple from the mock even when the action is a
 * warning; the headline names the state, so the colour does not have to carry
 * it (and `--color-attention` stays reserved for the answer buckets).
 */
export function HomeHeroCard({
  action,
  onAction,
}: {
  action: HomeNextAction;
  onAction: () => void;
}): JSX.Element {
  return (
    <section
      data-testid="home-next-up"
      className="rounded-xl bg-surface-container p-lg"
    >
      <div className="flex flex-col gap-lg md:flex-row md:items-center">
        <div
          aria-hidden
          className="flex size-14 shrink-0 items-center justify-center rounded-lg bg-primary-container text-on-primary-container"
        >
          <FileText size={26} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-ui-label text-on-surface-variant">次の一手</p>
          <h2 className="mt-xs break-words text-title-large font-semibold leading-ui">
            {action.headline}
          </h2>
          <p className="mt-xs break-words text-body-medium text-on-surface-variant">
            {action.detail}
          </p>
        </div>
        <button
          type="button"
          data-testid="home-next-up-action"
          onClick={onAction}
          className="inline-flex shrink-0 items-center justify-center gap-sm rounded-md bg-primary px-lg py-sm text-ui-label font-semibold text-on-primary hover:bg-primary-container focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-90 disabled:opacity-50"
          style={{
            transitionProperty: "background-color, opacity",
            transitionDuration: "var(--motion-duration-state-change)",
            transitionTimingFunction: "var(--motion-easing-standard)",
          }}
        >
          {action.actionLabel}
          <ArrowRight aria-hidden size={16} />
        </button>
      </div>
    </section>
  );
}
