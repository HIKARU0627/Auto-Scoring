import type { JSX } from "react";

import { AppRoutes } from "../core/app-routes.js";
import { useRouter } from "./router.js";

export const BACK_OR_HOME_BUTTON_TEST_ID = "app-back-or-home";

/**
 * Leading control every covered screen must expose (Issue #88 / INV-015).
 *
 * Pops one frame when the stack allows it; otherwise replaces to home so an
 * empty stack never leaves the user stranded.
 */
export function BackOrHomeButton(): JSX.Element {
  const { canPop, pop, replace } = useRouter();
  const label = canPop ? "前の画面へ戻る" : "ホームへ戻る";

  return (
    <button
      type="button"
      data-testid={BACK_OR_HOME_BUTTON_TEST_ID}
      aria-label={label}
      title={label}
      className="rounded-md border border-outline px-sm py-xs text-ui-label text-on-surface"
      onClick={() => {
        if (canPop) {
          pop();
          return;
        }
        replace(AppRoutes.home);
      }}
    >
      {canPop ? "←" : "⌂"}
    </button>
  );
}
