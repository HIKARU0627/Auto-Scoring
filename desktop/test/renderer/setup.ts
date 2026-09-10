import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import "../../src/renderer/styles/index.css";

/**
 * React Testing Library unmounts between tests only when a global `afterEach`
 * exists, and `globals: false` (vitest.config.ts) means there is none. Without
 * this file the second renderer test would find the first one's DOM still
 * mounted and `getByText` would start failing on duplicate matches -- the kind
 * of breakage that looks like a bug in the new test.
 */
afterEach(() => {
  cleanup();
  // Renderer tests stub `window.autoScoring`, since a test has no Electron main
  // process to talk to. Leaking one test's stub into the next would let a test
  // pass because of a bridge it never set up.
  vi.unstubAllGlobals();
});
