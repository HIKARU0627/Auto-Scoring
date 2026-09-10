import { render, type RenderResult } from "@testing-library/react";

import { AppShell } from "../../../src/renderer/AppShell.js";
import type { SidecarClient } from "../../../src/renderer/api/client.js";
import { ThemeProvider } from "../../../src/renderer/theme/ThemeProvider.js";
import {
  createMockSidecarClient,
  type MockSidecarHandlers,
} from "./mock-sidecar-client.js";

export function renderAppAt(
  location: string,
  options: {
    handlers?: MockSidecarHandlers;
    client?: SidecarClient;
    initialStack?: readonly string[];
  } = {},
): RenderResult {
  const client =
    options.client ?? createMockSidecarClient(options.handlers ?? {});

  return render(
    <ThemeProvider>
      <AppShell
        client={client}
        initialStack={options.initialStack ?? [location]}
      />
    </ThemeProvider>,
  );
}
