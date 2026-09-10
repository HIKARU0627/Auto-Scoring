import { vi } from "vitest";
import { render, type RenderResult } from "@testing-library/react";

import { AppShell } from "../../../src/renderer/AppShell.js";
import type { SidecarClient } from "../../../src/renderer/api/client.js";
import type { IntakeBridge } from "../../../src/renderer/api/intake-data.js";
import { ThemeProvider } from "../../../src/renderer/theme/ThemeProvider.js";
import {
  createMockSidecarClient,
  type MockSidecarHandlers,
} from "./mock-sidecar-client.js";

const DEFAULT_CONNECTION = {
  host: "127.0.0.1",
  port: 12345,
  token: "test-token",
};

export function renderAppAt(
  location: string,
  options: {
    handlers?: MockSidecarHandlers;
    client?: SidecarClient;
    bridge?: IntakeBridge;
    initialStack?: readonly string[];
  } = {},
): RenderResult {
  const client =
    options.client ?? createMockSidecarClient(options.handlers ?? {});

  vi.stubGlobal("autoScoring", {
    getAppInfo: vi.fn(async () => ({ version: "0.0.0", platform: "linux" })),
    chooseFolder: vi.fn(async () => "/tmp/batch"),
    scanFolder: vi.fn(async () => ({ name: "batch", entries: [] })),
    sidecarMultipartUpload: vi.fn(async () => ({ status: 200, body: {} })),
    ...options.bridge,
  });

  return render(
    <ThemeProvider>
      <AppShell
        client={client}
        connection={DEFAULT_CONNECTION}
        initialStack={options.initialStack ?? [location]}
      />
    </ThemeProvider>,
  );
}
