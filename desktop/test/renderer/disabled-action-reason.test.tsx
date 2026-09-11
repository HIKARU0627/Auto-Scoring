import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import {
  ActionRequirements,
  type ActionRequirement,
} from "../../src/renderer/core/action-requirements.js";
import { DisabledActionReason } from "../../src/renderer/features/intake/DisabledActionReason.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildApiKeySettings,
  buildApiKeyStatus,
} from "./support/mock-sidecar-client.js";

const REASON: ActionRequirement = {
  id: "test-reason",
  message: "上の欄を埋めてから、この操作を実行してください。",
};

const LONG_REASON: ActionRequirement = {
  id: "wrap-test",
  message:
    "回答欄が見つからなかった設問があります。このまま確定することもできますが、その設問は答案のページ全体を採点に送り、要確認として人の目に回りますので、設問名を押して枠を引いてください。",
};

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/** The elements a browser would Tab through, in document order (jsdom has no
 * sequential focus navigation -- same stand-in as `home-escape.test.tsx`). */
function sequentialFocusOrder(root: ParentNode): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((element) => element.tabIndex >= 0);
}

/** Pins the viewport to the 700x720 narrow window from INV-016. */
function withNarrowViewport(): () => void {
  const width = Object.getOwnPropertyDescriptor(window, "innerWidth");
  const height = Object.getOwnPropertyDescriptor(window, "innerHeight");

  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 700,
  });
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    value: 720,
  });
  window.dispatchEvent(new Event("resize"));

  return () => {
    if (width !== undefined) {
      Object.defineProperty(window, "innerWidth", width);
    }
    if (height !== undefined) {
      Object.defineProperty(window, "innerHeight", height);
    }
    window.dispatchEvent(new Event("resize"));
  };
}

describe("DisabledActionReason (INV-104/105/106/109)", () => {
  it("INV-104: renders nothing, and keeps no space, when there are no reasons", () => {
    const { container } = render(<DisabledActionReason requirements={[]} />);
    // `null`, not an empty wrapper: a wrapper would keep its margins and the
    // reason row would leave a gap after its condition is met.
    expect(container.innerHTML).toBe("");
  });

  it("INV-104: the reason disappears the moment its condition is met", () => {
    const { rerender } = render(
      <DisabledActionReason requirements={[REASON]} />,
    );
    expect(screen.getByTestId("disabled-reason-test-reason")).toBeDefined();

    rerender(<DisabledActionReason requirements={[]} />);

    expect(screen.queryByTestId("disabled-reason-test-reason")).toBeNull();
    expect(screen.queryByTestId("disabled-action-reason")).toBeNull();
  });

  it("INV-105: the reason is inline visible text, not a tooltip", () => {
    render(<DisabledActionReason requirements={[REASON]} />);

    const node = screen.getByTestId("disabled-reason-test-reason");
    expect(node.tagName).toBe("P");
    expect(node.textContent).toBe(REASON.message);
    // Nothing here relies on hover: no tooltip role, no title, no hiding.
    expect(node.closest('[role="tooltip"]')).toBeNull();
    expect(node.getAttribute("title")).toBeNull();
    expect(node.getAttribute("aria-hidden")).toBeNull();
  });

  it("INV-106: the reason can wrap inside a 700x720 window", () => {
    const restore = withNarrowViewport();
    try {
      render(<DisabledActionReason requirements={[LONG_REASON]} />);

      const node = screen.getByTestId("disabled-reason-wrap-test");
      const column = node.parentElement;
      expect(column).not.toBeNull();

      // The flex row can only shrink below the text's intrinsic width because
      // the text column is `min-w-0 flex-1`; without it the long reason runs
      // off the right edge instead of wrapping.
      expect(column?.className).toContain("min-w-0");
      expect(column?.className).toContain("flex-1");
      expect(node.className).toContain("break-words");
      expect(node.className).not.toContain("truncate");
      expect(node.className).not.toContain("whitespace-nowrap");
    } finally {
      restore();
    }
  });

  it("INV-109: the reason text never takes focus and the neighbour stays reachable", () => {
    render(
      <div>
        <DisabledActionReason requirements={[REASON]} />
        <button type="button">この操作を実行</button>
      </div>,
    );

    const reasonNode = screen.getByTestId("disabled-reason-test-reason");
    const button = screen.getByRole("button", { name: "この操作を実行" });
    const order = sequentialFocusOrder(document.body);

    expect(order).toContain(button);
    expect(order).not.toContain(reasonNode);
    expect(reasonNode.tabIndex).toBeLessThan(0);
  });
});

describe("INV-108: helperText and disabled reason are not shown twice", () => {
  it("shows the credential-store reason once, never repeated as input helper text", async () => {
    const message = ActionRequirements.credentialStoreUnavailable.message;

    renderAppAt(AppRoutes.settings, {
      handlers: {
        getApiKeySettings: async () =>
          buildApiKeySettings({
            keys: [buildApiKeyStatus({ id: "openrouter", configured: false })],
            store_unavailable_reason: "OSの資格情報ストアを利用できません。",
          }),
      },
    });

    fireEvent.click(await screen.findByTestId("settings-tab-api-key"));

    const reason = await screen.findByTestId(
      "disabled-reason-credential-store-unavailable",
    );
    expect(reason.textContent).toBe(message);

    // The input's own helper region must not repeat the reason: two copies of
    // the same sentence drift apart, and one of them ends up stale.
    const input = screen.getByTestId("settings-api-key-field-openrouter");
    const inputRegion = input.closest("div");
    expect(inputRegion?.textContent ?? "").not.toContain(message);
  });
});
