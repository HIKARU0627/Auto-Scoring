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
 * The application frame: a persistent sidebar beside the routed screen
 * (Issue #335). The sidebar only appears once the sidecar is usable, so the
 * startup and crash states keep the full window.
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
          <div className="flex min-h-screen bg-surface text-on-surface">
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
