import type { JSX } from "react";

import type { SidecarClient } from "./api/client.js";
import { SidecarApiProvider } from "./api/SidecarApiProvider.js";
import { AppRoutes } from "./core/app-routes.js";
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
 */
export function AppShell({
  client,
  initialStack = [AppRoutes.home],
}: {
  client: SidecarClient | null;
  initialStack?: readonly string[] | undefined;
}): JSX.Element {
  return (
    <SidecarApiProvider client={client}>
      <RouterProvider initialStack={initialStack}>
        {client === null ? (
          <SidecarConnectionPlaceholder />
        ) : (
          <div className="flex gap-xl bg-surface p-xl text-on-surface">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <RouteOutlet />
            </div>
          </div>
        )}
      </RouterProvider>
    </SidecarApiProvider>
  );
}
