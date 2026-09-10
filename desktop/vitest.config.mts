import { defineConfig } from "vitest/config";

// `.mts`, not `.ts`: this package is CommonJS (a sandboxed Electron preload
// script is loaded as CommonJS, so `src/main` and `src/preload` are compiled
// to CommonJS), and Vite's native config loader warns when it has to read an
// ESM config file through the CommonJS path.
/**
 * Two projects, because the tests here need opposite environments and mixing
 * them hides mistakes: a renderer test that accidentally reaches for `fs` must
 * fail, and an architecture test that reads the source tree needs `fs` to work.
 */
export default defineConfig({
  test: {
    testTimeout: 60000,
    hookTimeout: 60000,
    projects: [
      {
        test: {
          name: "renderer",
          environment: "jsdom",
          include: [
            "test/renderer/**/*.test.tsx",
            "test/renderer/**/*.test.ts",
          ],
          setupFiles: ["./test/renderer/setup.ts"],
          globals: false,
        },
      },
      {
        test: {
          name: "node",
          environment: "node",
          include: ["test/*.test.ts"],
          globals: false,
          testTimeout: 60000,
          hookTimeout: 60000,
        },
      },
    ],
  },
});
