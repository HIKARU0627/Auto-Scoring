import type { JSX } from "react";

import type { SidecarConnectionInfo } from "../shared/sidecar-upload.js";
import type { SidecarClient } from "./api/client.js";
import { SidecarApiProvider } from "./api/SidecarApiProvider.js";
import { AppRoutes } from "./core/app-routes.js";
import { RouteOutlet } from "./navigation/route-table.js";
import { RouterProvider } from "./navigation/router.js";

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

export function AppShell({
  client,
  connection = null,
  initialStack = [AppRoutes.home],
}: {
  client: SidecarClient | null;
  connection?: SidecarConnectionInfo | null;
  initialStack?: readonly string[];
}): JSX.Element {
  return (
    <SidecarApiProvider client={client} connection={connection}>
      <RouterProvider initialStack={initialStack}>
        {client === null ? <SidecarConnectionPlaceholder /> : <RouteOutlet />}
      </RouterProvider>
    </SidecarApiProvider>
  );
}
