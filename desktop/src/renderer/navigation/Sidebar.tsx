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
 */
export const SIDEBAR_PRODUCT_NAME = "Auto-Scoring";
/** Existing wording from `docs/simplified-design-specification.md` §1.1. */
export const SIDEBAR_PRODUCT_DESCRIPTION = "AI一次添削支援";

export function Sidebar(): JSX.Element {
  const { pathname, push } = useRouter();

  return (
    <aside
      data-testid={SIDEBAR_TEST_ID}
      className="sticky top-0 flex h-screen w-60 shrink-0 flex-col bg-surface-dim max-[900px]:w-16"
    >
      <div className="px-md pt-lg pb-md max-[900px]:px-xs max-[900px]:pt-md max-[900px]:pb-sm">
        <p className="text-[length:var(--font-size-title-large)] font-semibold leading-ui text-on-surface max-[900px]:hidden">
          {SIDEBAR_PRODUCT_NAME}
        </p>
        <p className="mt-xs text-[length:var(--font-size-label-medium)] leading-ui text-on-surface-variant max-[900px]:hidden">
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
        <ul className="flex flex-col gap-xs">
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
                    "flex w-full items-center gap-sm rounded-lg px-sm py-sm text-left text-ui-label",
                    "transition-colors duration-[var(--motion-duration-state-change)] ease-[var(--motion-easing-standard)]",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
                    "max-[900px]:justify-center max-[900px]:px-xs",
                    active
                      ? "bg-primary text-on-primary"
                      : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
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
