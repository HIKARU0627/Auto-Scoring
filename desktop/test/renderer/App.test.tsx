import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { App } from "../../src/renderer/App";
import { ThemeProvider } from "../../src/renderer/theme/ThemeProvider";

describe("App", () => {
  it("shows the sidecar placeholder before a client is available", async () => {
    render(
      <ThemeProvider>
        <App />
      </ThemeProvider>,
    );

    expect(screen.getByText("Auto-Scoring")).toBeDefined();
    expect(
      await screen.findByText("サイドカーの準備ができたらホームを表示します。"),
    ).toBeDefined();
  });
});
