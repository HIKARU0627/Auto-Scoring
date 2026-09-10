import { defineConfig } from "vite";

/**
 * Bundles the preload script into one self-contained CommonJS file.
 *
 * The main process is compiled by `tsc` instead (`tsconfig.main.json`), because
 * it can `require` its own files at runtime. **A sandboxed preload script
 * cannot.** Electron loads it through a restricted loader that resolves only
 * `electron` and a small allow-list, so `require("../shared/bridge")` fails at
 * startup with `module not found` -- the window opens, the bridge never
 * installs, and the renderer sees `window.autoScoring` as `undefined`. Turning
 * `sandbox` off would also "fix" it, at the cost of the isolation this whole
 * package is built around, so the preload is bundled rather than unsandboxed.
 */
export default defineConfig({
  build: {
    outDir: "out/preload",
    // `out/` also holds the tsc and renderer output; only this directory is ours.
    emptyOutDir: true,
    sourcemap: true,
    // A single entry, so everything it imports is inlined instead of being split
    // into a sibling chunk the sandboxed loader could not require either.
    lib: {
      entry: "src/preload/preload.ts",
      formats: ["cjs"],
      fileName: () => "preload.js",
    },
    rollupOptions: {
      // Provided by Electron at runtime; bundling it is neither possible nor wanted.
      external: ["electron"],
    },
  },
});
