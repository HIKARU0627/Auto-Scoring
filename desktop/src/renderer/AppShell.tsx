import type { JSX } from "react";

import type { SidecarClient } from "./api/client.js";
import { SidecarApiProvider } from "./api/SidecarApiProvider.js";
import { AppRoutes } from "./core/app-routes.js";
import { GradingUnavailableBanner } from "./core/GradingUnavailableBanner.js";
import { useGradingAvailability } from "./core/grading-availability.js";
import { RouteOutlet } from "./navigation/route-table.js";
import { RouterProvider } from "./navigation/router.js";
import { Sidebar } from "./navigation/Sidebar.js";

function SidecarConnectionPlaceholder(): JSX.Element {
  return (
    <main className="min-h-screen bg-surface p-xl text-on-surface">
      <h1 className="text-title-large font-medium leading-ui">Auto-Scoring</h1>
      <p className="mt-sm text-body-medium text-on-surface-variant">
        サイドカーの準備ができたらホームを表示します。
      </p>
    </main>
  );
}

/**
 * The application frame: a floating sidebar panel beside the routed screen
 * (Issue #335; panel inset in Issue #348). The sidebar only appears once the
 * sidecar is usable, so the startup and crash states keep the full window.
 *
 * Issue #348: `p-xl` around the frame is what makes the sidebar read as a
 * floating panel (mock: left edge x ~24, bottom edge clear of the window) and
 * `gap-xl` is the ~24px gutter between panel and content.
 *
 * Issue #375 item 4: `min-h-screen` forced the frame -- and with it the home
 * page's `flex-1` body -- to the window height, so a window taller than the
 * content left a band of bare surface under 最近のテスト. The frame is
 * content-height now; the window's own background (`html`/`body` are
 * `bg-surface`) covers any remainder instead of the layout being stretched to
 * fill it.
 *
 * Issue #398: the 採点不可バナー wraps the frame here, at the router top, so
 * it sits above every screen and is asked once per connection -- the place
 * `GradingAvailabilityResponse`'s schema documents ("keeps a banner above every
 * screen while `available` is false", INV-168).
 */
export function AppShell({
  client,
  initialStack = [AppRoutes.home],
}: {
  client: SidecarClient | null;
  initialStack?: readonly string[] | undefined;
}): JSX.Element {
  const gradingAvailability = useGradingAvailability(client);
  /**
   * Issue #422: the frame's height must account for the banner, not the other
   * way around. With the band mounted, the frame takes what the banner wrapper
   * leaves; without it, the frame fills the area the root left after the custom
   * title bar. Either way the frame row has a definite height, so the Sidebar
   * can stretch to it and the body column can size to its content --
   * `items-start` keeps the latter from being stretched to the window (Issue
   * #375 item 4).
   *
   * Issue #428: the no-banner frame is `h-full`, not `h-dvh`. The renderer root
   * owns the viewport now and hands this component the space below the 36px
   * title bar; asking for `dvh` here would add that 36px back and reintroduce
   * the document scroll #427 removed.
   *
   * Issue #427: the body column is the only scroller. A sticky Sidebar inside
   * this frame could not work while the window scrolled: `position: sticky` is
   * clamped to its containing block, and the frame's box ends at the viewport
   * even when its content is taller, so the panel left the screen as soon as the
   * content did. Bounding the column (`max-h-full` against the frame's definite
   * height) and giving it `overflow-y-auto` keeps the document at the viewport
   * and scrolls the routed screen inside the column instead, which leaves the
   * Sidebar -- and the 採点不可バナー above it -- in place. `max-h-full` also
   * keeps the column content-height when the screen is short, so the bare band
   * Issue #375 item 4 removed cannot come back.
   */
  const bannerVisible =
    gradingAvailability !== null && !gradingAvailability.available;

  return (
    <SidecarApiProvider client={client}>
      <RouterProvider initialStack={initialStack}>
        {client === null ? (
          <SidecarConnectionPlaceholder />
        ) : (
          <GradingUnavailableBanner availability={gradingAvailability}>
            <div
              data-testid="app-shell-frame"
              className={`flex items-start gap-xl bg-surface p-xl text-on-surface ${
                bannerVisible ? "min-h-0 flex-1" : "h-full"
              }`}
            >
              <Sidebar />
              <div
                data-testid="app-shell-content"
                className="flex min-h-0 max-h-full min-w-0 flex-1 flex-col overflow-y-auto"
              >
                <RouteOutlet />
              </div>
            </div>
          </GradingUnavailableBanner>
        )}
      </RouterProvider>
    </SidecarApiProvider>
  );
}
