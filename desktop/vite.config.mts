import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

/**
 * Renderer bundle only. The main process and the preload script are compiled by
 * `tsc` (`tsconfig.main.json`), because they ship as CommonJS for the sandboxed
 * preload and gain nothing from being bundled.
 */
export default defineConfig({
  plugins: [tailwindcss()],
  // Electron loads the built page from the filesystem with `loadFile`, so the
  // asset URLs have to be relative rather than rooted at `/`.
  base: "./",
  build: {
    outDir: "out/renderer",
    emptyOutDir: true,
    // The renderer is shipped inside the app, never served, so a map that makes
    // a crash report readable costs nothing.
    sourcemap: true,
  },
});
