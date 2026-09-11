import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import "../../src/renderer/styles/index.css";

/**
 * React Testing Library unmounts between tests only when a global `afterEach`
 * exists, and `globals: false` (vitest.config.ts) means there is none. Without
 * this file the second renderer test would find the first one's DOM still
 * mounted and `getByText` would start failing on duplicate matches -- the kind
 * of breakage that looks like a bug in the new test.
 */
class ResizeObserverMock implements ResizeObserver {
  private readonly observed = new Set<Element>();
  private readonly timers = new Set<ReturnType<typeof setTimeout>>();

  constructor(private readonly callback: ResizeObserverCallback) {}

  private notify(target: Element): void {
    const rect = target.getBoundingClientRect();
    const width = rect.width > 0 ? rect.width : 600;
    const height = rect.height > 0 ? rect.height : 848;
    this.callback(
      [
        {
          contentRect: new DOMRect(0, 0, width, height),
          target,
        } as ResizeObserverEntry,
      ],
      this,
    );
  }

  observe(target: Element): void {
    this.observed.add(target);
    // 同期で1回通知する。既存テストはこの通知だけで測位が完了する前提。
    this.notify(target);
    // 非同期でもう一度通知する。React Flow は `observe` の同期通知時点では
    // まだコンテナの ref を store に登録しておらず、ハンドルの寸法確定に
    // 失敗する（エッジが描かれない）。実ブラウザではレイアウト後に再度
    // 発火するので、同じ順序を timer で再現する。
    const timer = setTimeout(() => {
      this.timers.delete(timer);
      if (this.observed.has(target)) {
        this.notify(target);
      }
    }, 0);
    this.timers.add(timer);
  }

  unobserve(target: Element): void {
    this.observed.delete(target);
  }

  disconnect(): void {
    this.observed.clear();
    for (const timer of this.timers) {
      clearTimeout(timer);
    }
    this.timers.clear();
  }
}

/**
 * React Flow (`@xyflow/react`) の jsdom 用 shim。
 *
 * jsdom では `offsetWidth` / `offsetHeight` が常に 0 で、`window.DOMMatrixReadOnly`
 * も無い。この2つが欠けると React Flow はノードのハンドル寸法を確定できず、
 * エッジを1本も描かない。実ブラウザと同じ測位経路を通すため、React Flow の
 * 要素にだけ非ゼロ寸法を返す（他コンポーネントの「0 前提」の測位は変えない）。
 */
const RF_MEASURED_WIDTH = 220;
const RF_MEASURED_HEIGHT = 64;
for (const [prop, value] of [
  ["offsetWidth", RF_MEASURED_WIDTH],
  ["offsetHeight", RF_MEASURED_HEIGHT],
] as const) {
  const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, prop);
  Object.defineProperty(HTMLElement.prototype, prop, {
    configurable: true,
    get(this: HTMLElement) {
      if (this.closest?.(".react-flow")) {
        return value;
      }
      return original?.get?.call(this) ?? 0;
    },
  });
}

if (typeof window.DOMMatrixReadOnly === "undefined") {
  class DOMMatrixReadOnlyMock {
    readonly m22 = 1;
    constructor(_transform?: string) {}
  }
  (window as unknown as { DOMMatrixReadOnly: unknown }).DOMMatrixReadOnly =
    DOMMatrixReadOnlyMock;
}

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = function hasPointerCapture() {
    return true;
  };
  Element.prototype.setPointerCapture = function setPointerCapture() {};
  Element.prototype.releasePointerCapture = function releasePointerCapture() {};
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
});

afterEach(() => {
  cleanup();
  // Renderer tests stub `window.autoScoring`, since a test has no Electron main
  // process to talk to. Leaking one test's stub into the next would let a test
  // pass because of a bridge it never set up.
  vi.unstubAllGlobals();
  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
});
