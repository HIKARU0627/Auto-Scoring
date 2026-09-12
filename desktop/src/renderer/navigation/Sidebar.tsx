import type { JSX } from "react";

import { SidebarNavIcon } from "./SidebarNavIcon.js";
import { isSidebarItemActive, SIDEBAR_NAV_ITEMS } from "./sidebar-nav.js";
import { useRouter } from "./router.js";

export const SIDEBAR_TEST_ID = "app-sidebar";
export const SIDEBAR_NAV_TEST_ID = "app-sidebar-nav";

/**
 * Persistent left navigation (Issue #335, parent #333).
 *
 * The product name is the real one; there is no account in this product, so
 * the mock's user block is deliberately absent (`#333` ruling 4). Below the
 * wide breakpoint (`--layout-narrow-breakpoint`, 900px) the labels collapse to
 * icons so a 700px window keeps its content width instead of scrolling.
 *
 * Issue #348: the mock draws the sidebar as a floating, rounded panel inset
 * from the window edges (left ~24px, width ~208px, ~24px from the bottom), not
 * a full-bleed column. The panel stretches to the shell row (`self-stretch`
 * against the row's `items-start`) rather than a literal `100vh`, so it stays a
 * panel while the window scrolls and shrinks with the 採点不可バナー instead of
 * overflowing it (Issue #422); the nav rows use a ~48px row with a 12px gap to
 * match the mock's ~45px height / ~62px pitch.
 */
export const SIDEBAR_PRODUCT_NAME = "Auto-Scoring";
/** Existing wording from `docs/simplified-design-specification.md` §1.1. */
export const SIDEBAR_PRODUCT_DESCRIPTION = "AI一次添削支援";

export function Sidebar(): JSX.Element {
  const { pathname, push } = useRouter();

  return (
    <aside
      data-testid={SIDEBAR_TEST_ID}
      className="sticky top-xl flex w-52 shrink-0 self-stretch flex-col rounded-xl bg-surface-dim max-[900px]:w-16"
    >
      <div className="px-md pt-xl pb-xl max-[900px]:px-xs max-[900px]:pt-md max-[900px]:pb-sm">
        {/* Issue #371 item 6 dropped the 22px wordmark to 16px to stop it
            competing with the 28px ホーム heading. Issue #375 item 9: the mock's
            brand glyph is 15px (ascender-to-baseline) and the 16px font rendered
            only 12px, 20% under the mock. With the page heading back up to 48px
            (Issue #375 item 8) the wordmark can return to title-large (22px),
            whose glyph sits in the measured 15-17px band. */}
        <p className="text-[length:var(--font-size-title-large)] font-semibold leading-ui text-on-surface max-[900px]:hidden">
          {SIDEBAR_PRODUCT_NAME}
        </p>
        <p className="mt-xs text-[length:var(--font-size-label-medium)] leading-ui text-sidebar-subtitle max-[900px]:hidden">
          {SIDEBAR_PRODUCT_DESCRIPTION}
        </p>
        <p
          aria-hidden
          className="hidden select-none text-center text-[length:var(--font-size-title-medium)] font-semibold leading-ui text-on-surface max-[900px]:block"
        >
          AS
        </p>
      </div>

      <nav
        aria-label="メインナビゲーション"
        data-testid={SIDEBAR_NAV_TEST_ID}
        className="min-w-0 flex-1 px-md max-[900px]:px-xs"
      >
        <ul className="flex flex-col gap-md">
          {SIDEBAR_NAV_ITEMS.map((item) => {
            const active = isSidebarItemActive(pathname, item.route);
            return (
              <li key={item.route}>
                <button
                  type="button"
                  data-testid={item.testId}
                  aria-label={item.label}
                  aria-current={active ? "page" : undefined}
                  title={item.label}
                  onClick={() => {
                    if (!active) {
                      push(item.route);
                    }
                  }}
                  className={[
                    "flex min-h-12 w-full items-center gap-lg rounded-lg px-md py-sm text-left text-ui-label",
                    "transition-colors duration-[var(--motion-duration-state-change)] ease-[var(--motion-easing-standard)]",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
                    "max-[900px]:justify-center max-[900px]:px-xs",
                    active
                      ? "bg-primary text-on-primary"
                      : "text-sidebar-nav-idle hover:bg-surface-container hover:text-on-surface",
                  ].join(" ")}
                >
                  <SidebarNavIcon route={item.route} />
                  <span className="truncate max-[900px]:hidden">
                    {item.label}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
