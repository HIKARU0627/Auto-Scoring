import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "../../src/renderer/App";

/**
 * Vitest + React Testing Library foundation (Issue #217). One real test, so the
 * setup is known to run rather than merely configured.
 *
 * It also shows the shape every later renderer test takes: the bridge is a stub
 * on `window`, because in a test there is no Electron main process and the
 * renderer is not allowed to reach one directly.
 */
describe("App", () => {
  function stubBridge(version: string, platform: string): void {
    vi.stubGlobal("autoScoring", {
      getAppInfo: vi.fn().mockResolvedValue({ version, platform }),
    });
  }

  it("shows what the preload bridge reports", async () => {
    stubBridge("0.1.0", "win32");

    render(<App />);

    expect(await screen.findByText("version 0.1.0 / win32")).toBeDefined();
  });
});
