import { ArrowLeft, Home } from "lucide-react";
import type { JSX } from "react";

import { AppRoutes } from "../core/app-routes.js";
import { secondaryButtonClass } from "../features/ui/screen-ui.js";
import { useRouter } from "./router.js";

export const BACK_OR_HOME_BUTTON_TEST_ID = "app-back-or-home";

/**
 * Leading control every covered screen must expose (Issue #88 / INV-015).
 *
 * Pops one frame when the stack allows it; otherwise replaces to home so an
 * empty stack never leaves the user stranded.
 *
 * Issue #447: the glyphs were raw characters (`←` / `⌂`). This app ships no
 * icon font and CSP `default-src 'none'` blocks loading one (Issue #392), so a
 * character's weight, size, and baseline came from whatever font fell through
 * -- different on every machine, and visibly off against the secondary
 * controls around it. The control now draws a bundled `lucide-react` SVG like
 * the rest of the app and borrows the shared secondary button treatment
 * (`secondaryButtonClass`), so hover / active / focus / disabled match.
 *
 * The accessible name stays on the button (`aria-label` + `title`), not the
 * icon: colour or shape alone never carries the state.
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
      className={secondaryButtonClass()}
      onClick={() => {
        if (canPop) {
          pop();
          return;
        }
        replace(AppRoutes.home);
      }}
    >
      {canPop ? (
        <ArrowLeft aria-hidden className="size-4" />
      ) : (
        <Home aria-hidden className="size-4" />
      )}
    </button>
  );
}
