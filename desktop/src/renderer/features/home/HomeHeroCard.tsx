import type { JSX } from "react";
import { ArrowRight } from "lucide-react";

import { AppRoutes } from "../../core/app-routes.js";
import type { HomeNextAction } from "../../core/home-dashboard.js";
import { NavGlyph } from "../../navigation/SidebarNavIcon.js";

/**
 * 「次の一手」hero card (Issue #336, parent #333 §5). The one thing to press
 * now: a purple icon tile, the headline and reason, and the primary action on
 * the right (it moves under the text on narrow windows).
 *
 * The tile stays the primary purple from the mock even when the action is a
 * warning; the headline names the state, so the colour does not have to carry
 * it (and `--color-attention` stays reserved for the answer buckets).
 *
 * Issue 375 item 10: `justify-between` plus `flex-1 max-w-112` on the text
 * spread tile / text / CTA apart and left ~494px of dead space inside the card.
 * The tile and the text are one left-aligned group now; only the CTA is pushed
 * to the right, and the group takes the leftover width.
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
      className="h-full rounded-xl bg-surface-container-high p-xl"
    >
      <div className="flex h-full flex-col gap-lg md:flex-row md:items-center md:gap-xl">
        <div className="flex min-w-0 flex-1 items-center gap-xl">
          <div
            aria-hidden
            className="flex size-20 shrink-0 items-center justify-center rounded-lg bg-primary text-on-primary"
          >
            {/* Issue 360: the mock tile is 83px and its glyph is filled (ink
                ~66%); the 72px outline glyph read as a thin line drawing.
                Issue 371 item 5: the mock icon is the ruled document the sidebar
                uses, not lucide's plain `FileText`. */}
            <NavGlyph route={AppRoutes.intake} size={36} />
          </div>
          <div className="min-w-0 flex-1">
            {/* The mock stacks three levels inside the hero: accent text /
                pure-white heading / brighter secondary body (Issue 360, 371). */}
            <p className="text-ui-label text-primary-text">次の一手</p>
            <h2 className="mt-xs break-words text-title-large font-semibold leading-ui text-heading">
              {action.headline}
            </h2>
            <p className="mt-xs break-words text-body-medium text-on-surface-strong">
              {action.detail}
            </p>
          </div>
        </div>
        <button
          type="button"
          data-testid="home-next-up-action"
          onClick={onAction}
          className="inline-flex min-h-12 shrink-0 items-center justify-center gap-sm rounded-md bg-primary px-lg py-sm text-ui-label font-semibold text-on-primary hover:bg-primary-container focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-90 disabled:opacity-50"
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
